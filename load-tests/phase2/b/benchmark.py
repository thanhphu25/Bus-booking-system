import argparse
import base64
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import random
import re
import secrets
import subprocess
import sys
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import psutil
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
import requests


HERE = Path(__file__).resolve().parent
P1_SHA = "fd6b5f3026412d2359d70bfad681fc0773c8bcae"
API = "http://127.0.0.1:8085"
JAVA_FLAGS = ["-Xms256m", "-Xmx1024m", "-Duser.timezone=UTC"]
POOL = 10
WARMUP_INTENTS = 100
FIXTURE_PASSWORD = "Phase2FixtureOnly!"


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def queries(connection, user):
    rows = connection.execute("""
        SELECT queryid, query, calls, total_exec_time AS exec_ms, rows
        FROM pg_stat_statements
        WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
          AND userid = (SELECT oid FROM pg_roles WHERE rolname = %s)
        """, (user,))
    return {row["queryid"]: row for row in rows}


def sql_delta(before, after):
    result = []
    for query_id, row in after.items():
        previous = before.get(query_id, {})
        changed = {**row, **{key: row[key] - previous.get(key, 0) for key in ("calls", "exec_ms", "rows")}}
        if changed["calls"] > 0:
            result.append(changed)
    return sorted(result, key=lambda row: (-row["calls"], row["query"]))


def workload(trip_ids, warmup_ids, repeats, seed):
    rng = random.Random(seed)
    order = rng.sample(trip_ids, len(trip_ids))
    retry_set = rng.sample(range(len(order)), repeats)
    sequential = set(retry_set[:(repeats + 1) // 2])
    concurrent = set(retry_set[(repeats + 1) // 2:])

    def intent(label, index, trip_id, mode):
        identifier = f"{label}-{index + 1:05d}"
        return {"intent_id": identifier, "mode": mode, "key": identifier, "user": index % 4,
                "payload": {"tripId": trip_id, "passengerName": identifier,
                            "passengerPhone": "0901234567", "quantity": 1}}

    first_only = [intent("B", index, trip_id, "single") for index, trip_id in enumerate(order)]
    retry = [{**item, "mode": "sequential" if index in sequential else
              "concurrent" if index in concurrent else "single"} for index, item in enumerate(first_only)]
    warmup = [intent("W", index, trip_id, "single") for index, trip_id in enumerate(warmup_ids)]
    return {"first-only": first_only, "retry": retry, "warmup": warmup}


@contextmanager
def backend(args, jar, db, user, password, log, environment):
    process_env = {**environment, "DB_URL": f"jdbc:postgresql://127.0.0.1:{args.pg_port}/{db}",
                   "DB_USERNAME": user, "DB_PASSWORD": password}
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen([str(args.java), *JAVA_FLAGS, "-jar", str(jar)], env=process_env,
                                   stdout=stream, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 150
        while process.poll() is None and time.monotonic() < deadline:
            try:
                if requests.get(API + "/api/trips/1", timeout=2).status_code in (200, 404):
                    break
            except requests.RequestException:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError(f"Backend failed to start: {log}")
        yield process
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def login():
    tokens = []
    for index in range(1, 5):
        response = requests.post(API + "/api/auth/login",
                                 json={"email": f"phase2-b-{index}@example.test", "password": FIXTURE_PASSWORD},
                                 timeout=10)
        response.raise_for_status()
        tokens.append(response.json()["token"])
    return tokens


def sample_resources(processes):
    sample = []
    timestamp = time.monotonic_ns()
    for group, pid in processes.items():
        try:
            root = psutil.Process(pid)
            members = [root, *root.children(recursive=True)] if group == "postgresql" else [root]
        except psutil.NoSuchProcess:
            continue
        for process in members:
            try:
                with process.oneshot():
                    cpu = process.cpu_times()
                    sample.append({"timestamp_ns": timestamp, "group": group, "pid": process.pid,
                                   "cpu_seconds": cpu.user + cpu.system, "rss_bytes": process.memory_info().rss})
            except psutil.NoSuchProcess:
                continue
    return sample


def run_locust(args, suite, prefix, tokens, java_pid, measure):
    env = {**os.environ, "BOOKING_SUITE": str(suite), "BOOKING_OUTPUT": str(prefix),
           "BOOKING_TOKENS": json.dumps(tokens)}
    command = [sys.executable, "-m", "locust", "-f", str(HERE / "locustfile.py"), "--headless", "--only-summary",
               "--host", API, "--users", str(args.users), "--spawn-rate", str(args.users * 10),
               "--exit-code-on-error", "0", "--run-time", "8m"]
    records = []
    with prefix.with_suffix(".log").open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(command, env=env, stdout=stream, stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                if measure:
                    records.extend(sample_resources({"java": java_pid, "postgresql": args.pg_pid, "locust": process.pid}))
                time.sleep(0.2)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    if measure:
        write_csv(prefix.parent / "resources.csv", ("timestamp_ns", "group", "pid", "cpu_seconds", "rss_bytes"), records)
    if process.returncode or not prefix.with_suffix(".json").exists():
        raise RuntimeError(f"Locust failed: {prefix.with_suffix('.log')}")
    stats = json.loads(prefix.with_suffix(".json").read_text(encoding="utf-8"))
    return stats, read_csv(prefix.with_suffix(".csv")), records


def resource_summary(samples, start_ns, end_ns):
    by_group = defaultdict(lambda: defaultdict(dict))
    for row in samples:
        timestamp = row["timestamp_ns"]
        if start_ns <= timestamp <= end_ns:
            by_group[row["group"]][timestamp][row["pid"]] = row
    summary = {}
    for group, timestamps in by_group.items():
        frames = list(timestamps.values())
        cpu = sum(max(0, after[pid]["cpu_seconds"] - before[pid]["cpu_seconds"])
                  for before, after in zip(frames, frames[1:]) for pid in before.keys() & after.keys())
        peak = max(sum(row["rss_bytes"] for row in frame.values()) for frame in frames)
        summary[group] = {"samples": len(frames), "sampled_seconds": (max(timestamps) - min(timestamps)) / 1e9,
                          "cpu_seconds_sampled": cpu if len(frames) > 1 else None,
                          "peak_rss_mib": peak / 1024**2}
    return summary


def latency(rows):
    timings = sorted(float(row["duration_ms"]) for row in rows)
    return {"requests": len(timings), **{
        f"p{percent}": timings[math.ceil(percent * len(timings) / 100) - 1] if timings else None
        for percent in (50, 95)
    }}


def reconcile(connection, jobs, requests_log, output, variant):
    trip_ids = [job["payload"]["tripId"] for job in jobs]
    bookings = connection.execute("""
        SELECT id, user_id, trip_id, passenger_name, quantity, status
        FROM bookings WHERE trip_id = ANY(%s) ORDER BY id
        """, (trip_ids,)).fetchall()
    seats = connection.execute("""
        SELECT t.id AS trip_id, v.seat_capacity, t.available_seats,
               COALESCE(SUM(b.quantity) FILTER (WHERE b.status = 'CONFIRMED'), 0) AS confirmed_seats
        FROM trips t JOIN vehicles v ON v.id = t.vehicle_id LEFT JOIN bookings b ON b.trip_id = t.id
        WHERE t.id = ANY(%s) GROUP BY t.id, v.seat_capacity ORDER BY t.id
        """, (trip_ids,)).fetchall()
    write_csv(output / "bookings.csv", ("id", "user_id", "trip_id", "passenger_name", "quantity", "status"), bookings)
    write_csv(output / "seats.csv", ("trip_id", "seat_capacity", "available_seats", "confirmed_seats"), seats)

    bookings_by_intent = defaultdict(list)
    responses_by_intent = defaultdict(list)
    for row in bookings:
        bookings_by_intent[row["passenger_name"]].append(row)
    for row in requests_log:
        responses_by_intent[row["intent_id"]].append(row)

    details = []
    for job in jobs:
        intent = job["intent_id"]
        stored = bookings_by_intent[intent]
        logged = responses_by_intent[intent]
        confirmed = sum(row["quantity"] for row in stored if row["status"] == "CONFIRMED")
        status_counts = Counter(int(row["status"]) for row in logged if not row["error"])
        attempts = 1 if job["mode"] == "single" else 2
        expected = Counter({201: attempts}) if variant == "P1" else Counter({201: 1, 200: attempts - 1})
        sequential_order = (job["mode"] != "sequential" or variant == "P1" or
                            all(int(row["status"]) == (201 if row["attempt"] == "first" else 200) for row in logged))
        overlap = None
        if job["mode"] == "concurrent" and len(logged) == 2:
            earlier, later = sorted(logged, key=lambda row: int(row["started_ns"]))
            overlap = int(later["started_ns"]) - int(earlier["started_ns"]) < float(earlier["duration_ms"]) * 1e6
        acknowledged = {int(row["booking_id"]) for row in logged if row["booking_id"]}
        details.append({"intent_id": intent, "mode": job["mode"], "requests": len(logged),
                        "overlapping": overlap,
                        "acknowledged": bool(status_counts), "bookings": len(stored), "confirmed_seats": confirmed,
                        "duplicate_bookings": max(0, len(stored) - 1), "extra_seats": max(0, confirmed - 1),
                        "matches": len(logged) == attempts and status_counts == expected and sequential_order and
                        len(stored) == expected[201] and confirmed == expected[201] and
                        acknowledged == {row["id"] for row in stored} and
                        all(row["trip_id"] == job["payload"]["tripId"] for row in stored)})
    write_csv(output / "intent_results.csv", tuple(details[0]), details)

    keys = []
    if variant == "B":
        keys = connection.execute("""
            SELECT k.user_id, k.idempotency_key, k.booking_id
            FROM booking_idempotency_keys k
            WHERE k.idempotency_key LIKE 'B-%' ORDER BY k.idempotency_key
            """).fetchall()
        write_csv(output / "keys.csv", ("user_id", "idempotency_key", "booking_id"), keys)
    known_bookings = {row["id"]: row for row in bookings}
    keys_match = variant == "P1" or (len(keys) == len(jobs) and all(
        row["booking_id"] in known_bookings and
        row["idempotency_key"] == known_bookings[row["booking_id"]]["passenger_name"] and
        row["user_id"] == known_bookings[row["booking_id"]]["user_id"] for row in keys))
    mismatches = sum(not row["matches"] for row in details)
    unbalanced = sum(row["available_seats"] < 0 or
                     row["available_seats"] + row["confirmed_seats"] != row["seat_capacity"] for row in seats)
    return {"intents": len(jobs), "acknowledged_intents": sum(row["acknowledged"] for row in details),
            "persisted_intents": sum(row["bookings"] > 0 for row in details), "bookings": len(bookings),
            "duplicate_bookings": sum(row["duplicate_bookings"] for row in details),
            "seats_deducted": sum(row["seat_capacity"] - row["available_seats"] for row in seats),
            "extra_seats": sum(row["extra_seats"] for row in details), "unbalanced_trips": unbalanced,
            "concurrent_pairs": sum(row["mode"] == "concurrent" for row in details),
            "overlapping_pairs": sum(row["overlapping"] is True for row in details),
            "intent_mismatches": mismatches, "keys_match": keys_match,
            "checked": keys_match and not mismatches and not unbalanced and len(seats) == len(jobs) and
            sum(row["bookings"] for row in details) == len(bookings)}


def run_trial(args, variant, workload_name, jobs, suite_path, warmup_path, output, db, connect, java_pid):
    with connect(db) as connection:
        connection.execute("ANALYZE")
        isolation = connection.execute("SHOW transaction_isolation").fetchone()["transaction_isolation"]
        if isolation != "read committed":
            raise RuntimeError(f"Unexpected PostgreSQL isolation: {isolation}")
        versions = connection.execute("SELECT version FROM flyway_schema_history WHERE success ORDER BY installed_rank")
        write_json(output / "flyway.json", [row["version"] for row in versions])
        key_table = connection.execute("SELECT to_regclass('booking_idempotency_keys') AS name").fetchone()["name"]
        if bool(key_table) != (variant == "B"):
            raise RuntimeError(f"Unexpected booking key schema for {variant}")

        tokens = login()
        warmup, warmup_requests, _ = run_locust(args, warmup_path, output / "warmup", tokens, java_pid, False)
        if warmup["unfinished_jobs"] or len(warmup_requests) != WARMUP_INTENTS or any(
                row["status"] != "201" or row["error"] for row in warmup_requests):
            raise RuntimeError(f"Warm-up failed: {output}")

        before = queries(connection, args.app_db_user)
        started_at = utc()
        timing, requests_log, samples = run_locust(args, suite_path, output / "requests", tokens, java_pid, True)
        ended_at = utc()
        sql_rows = sql_delta(before, queries(connection, args.app_db_user))
        write_csv(output / "sql.csv", ("queryid", "query", "calls", "exec_ms", "rows"), sql_rows)
        counts = reconcile(connection, jobs, requests_log, output, variant)

    start_ns, end_ns = timing["start_ns"], timing["end_ns"]
    elapsed = (end_ns - start_ns) / 1e9 if start_ns and end_ns and end_ns > start_ns else None
    successes = [row for row in requests_log if not row["error"]]
    metrics = {"variant": variant, "workload": workload_name, "started_at_utc": started_at, "ended_at_utc": ended_at,
               "seconds": elapsed, "requests": len(requests_log), "successful_requests": len(successes),
               "errors": dict(Counter(f"{row['status']}:{row['error']}" for row in requests_log if row["error"])),
               "http_statuses": dict(Counter(row["status"] for row in requests_log)),
               "rps": len(requests_log) / elapsed if elapsed else None,
               "successful_rps": len(successes) / elapsed if elapsed else None,
               "response_bytes": sum(int(row["response_bytes"]) for row in requests_log),
               "sql_calls": sum(row["calls"] for row in sql_rows),
               "latency_ms": {
                   "first_attempt": latency([row for row in successes if row["attempt"] == "first"]),
                   "retry_attempt": latency([row for row in successes if row["attempt"] == "retry"]),
                   "created_201": latency([row for row in successes if row["status"] == "201"]),
                   "replayed_200": latency([row for row in successes if row["status"] == "200"])},
               "resources": resource_summary(samples, start_ns, end_ns) if elapsed else {}, **counts}
    metrics["checked"] = counts["checked"] and elapsed is not None and timing["unfinished_jobs"] == 0 and not metrics["errors"]
    write_json(output / "metrics.json", metrics)
    return metrics


def flatten(metrics, repetition):
    names = ("variant", "workload", "requests", "successful_requests", "intents", "acknowledged_intents",
             "persisted_intents", "bookings", "duplicate_bookings", "seats_deducted", "extra_seats", "unbalanced_trips",
             "intent_mismatches", "concurrent_pairs", "overlapping_pairs", "seconds", "rps", "successful_rps",
             "sql_calls", "checked")
    return {"repetition": repetition, **{name: metrics[name] for name in names}, **{
        f"{group}_{percentile}_ms": stats[percentile]
        for group, stats in metrics["latency_ms"].items() for percentile in ("p50", "p95")
    }}


def summarize_trials(rows, output):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["variant"], row["workload"])].append(row)
    result = []
    for (variant, workload_name), group in groups.items():
        for metric in ("first_attempt_p95_ms", "retry_attempt_p95_ms", "replayed_200_p95_ms", "successful_rps"):
            values = [row[metric] for row in group if row[metric] is not None]
            if values:
                result.append({"variant": variant, "workload": workload_name, "metric": metric,
                               "trials": len(values), "median": median(values), "min": min(values), "max": max(values)})
    write_csv(output / "aggregate.csv", ("variant", "workload", "metric", "trials", "median", "min", "max"), result)


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    session = secrets.token_hex(4)
    base = f"busb_b_base_{session}"
    args.app_db_user = f"busb_b_app_{session}"
    password = secrets.token_urlsafe(30)
    pg_password = os.environ.get("PHASE2_PG_PASSWORD", "")

    def connect(db="postgres"):
        return psycopg.connect(host="127.0.0.1", port=args.pg_port, dbname=db, user="postgres",
                               password=pg_password, autocommit=True, row_factory=dict_row)

    environment = {**os.environ, "SPRING_PROFILES_ACTIVE": "dev", "SERVER_PORT": "8085",
                   "SERVER_ADDRESS": "127.0.0.1", "SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE": str(POOL),
                   "JWT_SECRET": base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
                   "EMAIL_OTP_SECRET": base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
                   "BOOTSTRAP_SUPER_ADMIN_ENABLED": "false"}
    environment.pop("PHASE2_PG_PASSWORD", None)
    java_version = subprocess.run([str(args.java), "-version"], capture_output=True, text=True, check=True).stderr.strip()
    cpuinfo = Path("/proc/cpuinfo")
    model = re.search(r"^model name\s*:\s*(.+)$", cpuinfo.read_text(), re.MULTILINE) if cpuinfo.is_file() else None
    manifest = {"start_utc": utc(), "platform": platform.platform(), "cpu_model": model[1] if model else platform.processor(),
                "cpu_logical": psutil.cpu_count(), "ram_bytes": psutil.virtual_memory().total, "jdk": java_version,
                "java_flags": JAVA_FLAGS, "hikari_max_pool": POOL, "python": platform.python_version(),
                "packages": {name: importlib.metadata.version(name) for name in ("locust", "psutil", "psycopg", "requests")},
                "settings": {"seed": args.seed, "users": args.users, "max_in_flight": args.users,
                             "wait_seconds": 0, "spawn_rate": args.users * 10, "repetitions": args.repetitions,
                             "intents": args.intents, "retries": args.retries, "warmup_intents": WARMUP_INTENTS,
                             "fixture_trips": 1100, "seats_per_trip": 4, "users_in_fixture": 4},
                "source": {variant: {"source_sha": sha, "source_working_tree": "clean (reported at build)",
                                     "jar_name": jar.name, "jar_sha256": sha256(jar)}
                           for variant, sha, jar in (("P1", P1_SHA, args.p1_jar), ("B", args.b_sha, args.b_jar))},
                "input_sha256": {name: sha256(HERE / name) for name in ("benchmark.py", "locustfile.py", "fixture.sql")}}
    summary = []
    with connect() as admin:
        settings = admin.execute("""
            SELECT name, setting, unit FROM pg_settings WHERE name IN (
                'server_version', 'default_transaction_isolation', 'shared_buffers', 'shared_preload_libraries',
                'max_connections', 'lock_timeout', 'statement_timeout', 'synchronous_commit', 'pg_stat_statements.track')
            ORDER BY name
            """)
        manifest["postgresql"] = settings.fetchall()
        write_json(args.output / "manifest.json", manifest)
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(args.app_db_user), sql.Literal(password)))
        try:
            admin.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(base), sql.Identifier(args.app_db_user)))
            with backend(args, args.p1_jar, base, args.app_db_user, password, args.output / "snapshot_backend.log", environment):
                pass
            with connect(base) as connection:
                schema = connection.execute("SELECT MAX(installed_rank) AS rank FROM flyway_schema_history").fetchone()
                if schema["rank"] != 16:
                    raise RuntimeError("The P1 JAR must build the V1–V16 snapshot")
                connection.execute("CREATE EXTENSION pg_stat_statements")
                connection.execute("SET TIME ZONE 'UTC'")
                connection.execute((HERE / "fixture.sql").read_text(encoding="utf-8"))
                trips = connection.execute("""
                    SELECT t.id, t.available_seats, v.seat_capacity
                    FROM trips t JOIN vehicles v ON v.id = t.vehicle_id ORDER BY t.departure_time, t.id
                    """).fetchall()
                if (len(trips) != 1100 or any(row["available_seats"] != 4 or row["seat_capacity"] != 4 for row in trips) or
                        connection.execute("SELECT count(*) AS n FROM bookings").fetchone()["n"]):
                    raise RuntimeError("The snapshot does not match the clean benchmark fixture")
            suites = workload([row["id"] for row in trips[:args.intents]],
                              [row["id"] for row in trips[1000:]], args.retries, args.seed)
            paths = {name: args.output / f"intents_{name}.json" for name in suites}
            for name, path in paths.items():
                write_json(path, suites[name])
            manifest["intent_sha256"] = {name: sha256(path) for name, path in paths.items()}
            write_json(args.output / "manifest.json", manifest)

            for rep in range(1, args.repetitions + 1):
                order = ("P1", "B") if rep % 2 else ("B", "P1")
                for name in ("first-only", "retry"):
                    for variant in order:
                        print(f"Run {rep}/{args.repetitions} | {name} | {variant}", flush=True)
                        output = args.output / f"{rep:02d}_{name}_{variant}"
                        output.mkdir()
                        db = f"busb_b_run_{session}"
                        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE {} OWNER {}").format(
                            sql.Identifier(db), sql.Identifier(base), sql.Identifier(args.app_db_user)))
                        try:
                            jar = args.p1_jar if variant == "P1" else args.b_jar
                            with backend(args, jar, db, args.app_db_user, password, output / "backend.log", environment) as java:
                                metrics = run_trial(args, variant, name, suites[name], paths[name], paths["warmup"],
                                                    output, db, connect, java.pid)
                        finally:
                            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(db)))
                        summary.append(flatten(metrics, rep))
                        write_csv(args.output / "summary.csv", tuple(summary[0]), summary)
                        if not metrics["checked"]:
                            raise RuntimeError(f"Request and DB reconciliation failed: {output}")
        finally:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(base)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(args.app_db_user)))
    write_json(args.output / "manifest.json", {**manifest, "end_utc": utc(), "completed_trials": len(summary)})
    summarize_trials(summary, args.output)


def parse_args():
    parser = argparse.ArgumentParser(description="BusBooking Phase 2 B paired benchmark")
    for argument in ("java", "p1-jar", "b-jar", "output"):
        parser.add_argument(f"--{argument}", type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument("--b-sha", required=True)
    parser.add_argument("--pg-port", type=int, required=True)
    parser.add_argument("--pg-pid", type=int, required=True)
    parser.add_argument("--seed", type=int, default=20261118)
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--intents", type=int, default=1000)
    parser.add_argument("--retries", type=int, default=200)
    args = parser.parse_args()
    if not 2 <= args.users or not 1 <= args.repetitions or not 2 <= args.retries <= args.intents <= 1000:
        parser.error("Require at least two users, one repetition, and 2 <= retries <= intents <= 1000")
    if not re.fullmatch(r"[a-f0-9]{40}", args.b_sha) or args.b_sha == P1_SHA:
        parser.error("Pass the full, distinct Git SHA used to build the B JAR")
    if sha256(args.p1_jar) == sha256(args.b_jar):
        parser.error("P1 and B must be different JARs")
    return args


if __name__ == "__main__":
    run(parse_args())
