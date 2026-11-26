"""BusBooking Phase 2C paired benchmark: P1 vs C on the create-booking write path.

Both JARs receive the same requests without Idempotency-Key, so they run the same create use case. The C JAR is
built from the Phase 2C branch, which also contains B (table V17 exists but is not used without a key).
"""
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
FIXTURE_PASSWORD = "Phase2FixtureOnly!"
PRICE = 150000
LEGACY_TRIPS, LEGACY_SEATS = 1000, 4
MAIN_TRIPS, MAIN_SEATS = 100, 40
WARMUP_TRIPS, WARMUP_PER_TRIP = 10, 10
WORKLOADS = ("legacy-distributed", "distributed", "concentrated")
RELATION_TABLES = ("routes", "locations", "vehicles", "bus_operators")
TABLE = re.compile(r"\b(trips|routes|locations|vehicles|bus_operators|bookings|users|roles|"
                   r"booking_idempotency_keys)\b", re.IGNORECASE)
LOCK = re.compile(r"\bfor (no key )?update\b", re.IGNORECASE)


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


# ---------------------------------------------------------------- SQL statistics

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
            changed["kind"] = (changed["query"].split(None, 1) or ["?"])[0].lower()
            changed["tables"] = " ".join(sorted({match.lower() for match in TABLE.findall(changed["query"])}))
            changed["group"] = classify(changed)
            result.append(changed)
    return sorted(result, key=lambda row: (-row["calls"], row["query"]))


def classify(row):
    tables = set(row["tables"].split())
    if tables & {"users", "roles"}:
        return "auth"  # JWT principal loading; identical in P1 and C, reported separately.
    if row["kind"] == "select" and tables & set(RELATION_TABLES):
        return "relation_select"
    if row["kind"] == "select" and "trips" in tables and LOCK.search(row["query"]):
        return "trip_lock_select"
    if row["kind"] == "update" and "trips" in tables:
        return "trip_seat_update"
    if row["kind"] == "insert" and "bookings" in tables:
        return "booking_insert"
    return "other"


def sql_summary(rows, bookings):
    by_group = defaultdict(lambda: {"calls": 0, "exec_ms": 0.0})
    by_table = defaultdict(int)
    for row in rows:
        by_group[row["group"]]["calls"] += row["calls"]
        by_group[row["group"]]["exec_ms"] += row["exec_ms"]
        if row["kind"] == "select" and row["group"] != "auth":
            for table in row["tables"].split():
                by_table[table] += row["calls"]
    per = (lambda value: value / bookings) if bookings else (lambda value: None)
    booking_rows = [row for row in rows if row["group"] != "auth"]
    return {
        "sql_calls": sum(row["calls"] for row in rows),
        "booking_sql_per_booking": per(sum(row["calls"] for row in booking_rows)),
        "booking_select_per_booking": per(sum(row["calls"] for row in booking_rows if row["kind"] == "select")),
        "relation_select_per_booking": per(by_group["relation_select"]["calls"]),
        "auth_sql_per_booking": per(by_group["auth"]["calls"]),
        "booking_sql_exec_ms": sum(row["exec_ms"] for row in booking_rows),
        "groups": {name: dict(value) for name, value in sorted(by_group.items())},
        "select_calls_by_table": dict(sorted(by_table.items())),
    }


# ---------------------------------------------------------------- workload

def workloads(legacy_ids, main_ids, warmup_ids, seed):
    rng = random.Random(seed)

    def intent(identifier, index, trip_id):
        return {"intent_id": identifier, "user": index % 4,
                "payload": {"tripId": trip_id, "passengerName": identifier,
                            "passengerPhone": "0901234567", "quantity": 1}}

    legacy = [intent(f"L-{index + 1:04d}", index, trip_id) for index, trip_id in enumerate(legacy_ids)]
    rng.shuffle(legacy)

    # The same 4,000 intents (40 per trip) in two orders: shuffled (distributed) and grouped by trip
    # (concentrated, so the in-flight requests compete for the same Trip row lock).
    trip_order = rng.sample(main_ids, len(main_ids))
    grouped = [intent(f"M-{trip_index + 1:03d}-{seat + 1:02d}", trip_index * MAIN_SEATS + seat, trip_id)
               for trip_index, trip_id in enumerate(trip_order) for seat in range(MAIN_SEATS)]
    distributed = rng.sample(grouped, len(grouped))

    warmup = [intent(f"W-{index + 1:03d}", index, trip_id)
              for index, trip_id in enumerate(trip_id for trip_id in warmup_ids for _ in range(WARMUP_PER_TRIP))]
    return {"legacy-distributed": legacy, "distributed": distributed, "concentrated": grouped, "warmup": warmup}


# ---------------------------------------------------------------- processes

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
                                 json={"email": f"phase2-c-{index}@example.test", "password": FIXTURE_PASSWORD},
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


def sample_locks(monitor, db, user):
    row = monitor.execute("""
        SELECT count(*) FILTER (WHERE state = 'active') AS active,
               count(*) FILTER (WHERE wait_event_type = 'Lock') AS lock_waiting
        FROM pg_stat_activity WHERE datname = %s AND usename = %s
        """, (db, user)).fetchone()
    return {"timestamp_ns": time.monotonic_ns(), **row}


def run_locust(args, users, suite, prefix, tokens, java_pid, monitor=None, db=None):
    env = {**os.environ, "BOOKING_SUITE": str(suite), "BOOKING_OUTPUT": str(prefix),
           "BOOKING_TOKENS": json.dumps(tokens)}
    command = [sys.executable, "-m", "locust", "-f", str(HERE / "locustfile.py"), "--headless", "--only-summary",
               "--host", API, "--users", str(users), "--spawn-rate", str(users * 10),
               "--exit-code-on-error", "0", "--run-time", "20m"]
    resources, locks = [], []
    with prefix.with_suffix(".log").open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(command, env=env, stdout=stream, stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                if monitor is not None:
                    resources.extend(sample_resources({"java": java_pid, "postgresql": args.pg_pid,
                                                       "locust": process.pid}))
                    locks.append(sample_locks(monitor, db, args.app_db_user))
                time.sleep(0.2)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    if monitor is not None:
        write_csv(prefix.parent / "resources.csv", ("timestamp_ns", "group", "pid", "cpu_seconds", "rss_bytes"),
                  resources)
        write_csv(prefix.parent / "locks.csv", ("timestamp_ns", "active", "lock_waiting"), locks)
    if process.returncode or not prefix.with_suffix(".json").exists():
        raise RuntimeError(f"Locust failed: {prefix.with_suffix('.log')}")
    stats = json.loads(prefix.with_suffix(".json").read_text(encoding="utf-8"))
    return stats, read_csv(prefix.with_suffix(".csv")), resources, locks


# ---------------------------------------------------------------- summaries

def resource_summary(samples, start_ns, end_ns):
    by_group = defaultdict(lambda: defaultdict(dict))
    for row in samples:
        if start_ns <= row["timestamp_ns"] <= end_ns:
            by_group[row["group"]][row["timestamp_ns"]][row["pid"]] = row
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


def lock_summary(samples, start_ns, end_ns):
    rows = [row for row in samples if start_ns <= row["timestamp_ns"] <= end_ns]
    if not rows:
        return {"samples": 0}
    return {"samples": len(rows),
            "mean_active": sum(row["active"] for row in rows) / len(rows),
            "mean_lock_waiting": sum(row["lock_waiting"] for row in rows) / len(rows),
            "fraction_samples_with_lock_wait": sum(row["lock_waiting"] > 0 for row in rows) / len(rows)}


def percentile(values, percent):
    values = sorted(values)
    return values[math.ceil(percent * len(values) / 100) - 1] if values else None


def reconcile(connection, jobs, requests_log, output):
    trip_ids = sorted({job["payload"]["tripId"] for job in jobs})
    expected_per_trip = Counter(job["payload"]["tripId"] for job in jobs)
    bookings = connection.execute("""
        SELECT id, user_id, trip_id, passenger_name, quantity, unit_price, total_amount, status
        FROM bookings WHERE trip_id = ANY(%s) ORDER BY id
        """, (trip_ids,)).fetchall()
    seats = connection.execute("""
        SELECT t.id AS trip_id, v.seat_capacity, t.available_seats,
               COALESCE(SUM(b.quantity) FILTER (WHERE b.status = 'CONFIRMED'), 0) AS confirmed_seats
        FROM trips t JOIN vehicles v ON v.id = t.vehicle_id LEFT JOIN bookings b ON b.trip_id = t.id
        WHERE t.id = ANY(%s) GROUP BY t.id, v.seat_capacity ORDER BY t.id
        """, (trip_ids,)).fetchall()
    write_csv(output / "bookings.csv", ("id", "user_id", "trip_id", "passenger_name", "quantity", "unit_price",
                                        "total_amount", "status"), bookings)
    write_csv(output / "seats.csv", ("trip_id", "seat_capacity", "available_seats", "confirmed_seats"), seats)

    stored = defaultdict(list)
    logged = defaultdict(list)
    for row in bookings:
        stored[row["passenger_name"]].append(row)
    for row in requests_log:
        logged[row["intent_id"]].append(row)

    details, canonical = [], []
    for job in jobs:
        intent = job["intent_id"]
        rows, responses = stored[intent], logged[intent]
        ok = (len(responses) == 1 and responses[0]["status"] == "201" and not responses[0]["error"] and
              len(rows) == 1 and rows[0]["status"] == "CONFIRMED" and rows[0]["quantity"] == 1 and
              rows[0]["trip_id"] == job["payload"]["tripId"] and rows[0]["unit_price"] == PRICE and
              rows[0]["total_amount"] == PRICE and str(rows[0]["id"]) == responses[0]["booking_id"])
        details.append({"intent_id": intent, "trip_id": job["payload"]["tripId"], "requests": len(responses),
                        "bookings": len(rows), "matches": ok})
        canonical.append([intent, job["payload"]["tripId"],
                          [[row["quantity"], str(row["unit_price"]), str(row["total_amount"]), row["status"]]
                           for row in rows], [row["status"] for row in responses]])
    write_csv(output / "intent_results.csv", ("intent_id", "trip_id", "requests", "bookings", "matches"), details)
    unbalanced = sum(row["available_seats"] < 0 or
                     row["available_seats"] + row["confirmed_seats"] != row["seat_capacity"] or
                     row["confirmed_seats"] != expected_per_trip[row["trip_id"]] for row in seats)
    mismatches = sum(not row["matches"] for row in details)
    return {"intents": len(jobs), "bookings": len(bookings),
            "seats_deducted": sum(row["seat_capacity"] - row["available_seats"] for row in seats),
            "unbalanced_trips": unbalanced, "intent_mismatches": mismatches,
            "body_keys": sorted({row["body_keys"] for row in requests_log if not row["error"]}),
            "outcome_sha256": hashlib.sha256(json.dumps(canonical).encode()).hexdigest(),
            "checked": not mismatches and not unbalanced and len(seats) == len(trip_ids) and
            len(bookings) == len(jobs)}


def run_trial(args, variant, users, workload_name, jobs, suite_path, warmup_path, output, db, connect, java_pid):
    with connect(db) as connection, connect(db) as monitor:
        connection.execute("ANALYZE")
        versions = [row["version"] for row in connection.execute(
            "SELECT version FROM flyway_schema_history WHERE success AND version IS NOT NULL ORDER BY installed_rank")]
        write_json(output / "flyway.json", versions)
        expected_max = "16" if variant == "P1" else "17"
        if versions[-1] != expected_max:
            raise RuntimeError(f"Unexpected Flyway version for {variant}: {versions[-1]}")

        tokens = login()
        warmup, warmup_requests, _, _ = run_locust(args, users, warmup_path, output / "warmup", tokens, java_pid)
        if warmup["unfinished_jobs"] or any(row["status"] != "201" or row["error"] for row in warmup_requests):
            raise RuntimeError(f"Warm-up failed: {output}")

        before = queries(connection, args.app_db_user)
        started_at = utc()
        timing, requests_log, resources, locks = run_locust(
            args, users, suite_path, output / "requests", tokens, java_pid, monitor, db)
        ended_at = utc()
        sql_rows = sql_delta(before, queries(connection, args.app_db_user))
        write_csv(output / "sql.csv", ("queryid", "group", "kind", "tables", "calls", "exec_ms", "rows", "query"),
                  sql_rows)
        counts = reconcile(connection, jobs, requests_log, output)

    start_ns, end_ns = timing["start_ns"], timing["end_ns"]
    elapsed = (end_ns - start_ns) / 1e9 if start_ns and end_ns and end_ns > start_ns else None
    successes = [row for row in requests_log if not row["error"]]
    timings = [float(row["duration_ms"]) for row in successes]
    resource = resource_summary(resources, start_ns, end_ns) if elapsed else {}
    per_booking = {f"{group}_cpu_s_per_booking": (resource.get(group, {}).get("cpu_seconds_sampled") or 0) /
                   counts["bookings"] if counts["bookings"] else None for group in ("java", "postgresql")}
    metrics = {"variant": variant, "workload": workload_name, "users": users, "started_at_utc": started_at,
               "ended_at_utc": ended_at, "seconds": elapsed, "requests": len(requests_log),
               "successful_requests": len(successes),
               "errors": dict(Counter(f"{row['status']}:{row['error']}" for row in requests_log if row["error"])),
               "http_statuses": dict(Counter(row["status"] for row in requests_log)),
               "successful_rps": len(successes) / elapsed if elapsed else None,
               "p50_ms": percentile(timings, 50), "p95_ms": percentile(timings, 95),
               "response_bytes": sum(int(row["response_bytes"]) for row in requests_log),
               "sql": sql_summary(sql_rows, counts["bookings"]), "resources": resource, **per_booking,
               "locks": lock_summary(locks, start_ns, end_ns) if elapsed else {}, **counts}
    metrics["checked"] = (counts["checked"] and elapsed is not None and timing["unfinished_jobs"] == 0 and
                          not metrics["errors"])
    write_json(output / "metrics.json", metrics)
    return metrics


SUMMARY_FIELDS = ("repetition", "variant", "workload", "users", "requests", "successful_requests", "bookings",
                  "seats_deducted", "unbalanced_trips", "intent_mismatches", "seconds", "successful_rps", "p50_ms",
                  "p95_ms", "booking_select_per_booking", "relation_select_per_booking", "booking_sql_per_booking",
                  "auth_sql_per_booking", "booking_sql_exec_ms", "java_cpu_s_per_booking",
                  "postgresql_cpu_s_per_booking", "java_peak_rss_mib", "mean_lock_waiting",
                  "fraction_samples_with_lock_wait", "checked")
AGGREGATE_METRICS = ("p50_ms", "p95_ms", "successful_rps", "booking_select_per_booking",
                     "relation_select_per_booking", "booking_sql_exec_ms", "java_cpu_s_per_booking",
                     "postgresql_cpu_s_per_booking", "mean_lock_waiting", "fraction_samples_with_lock_wait")


def flatten(metrics, repetition):
    return {"repetition": repetition, **{name: metrics.get(name) for name in SUMMARY_FIELDS if name in metrics},
            **{name: metrics["sql"][name] for name in ("booking_select_per_booking", "relation_select_per_booking",
                                                       "booking_sql_per_booking", "auth_sql_per_booking",
                                                       "booking_sql_exec_ms")},
            "java_peak_rss_mib": metrics["resources"].get("java", {}).get("peak_rss_mib"),
            "mean_lock_waiting": metrics["locks"].get("mean_lock_waiting"),
            "fraction_samples_with_lock_wait": metrics["locks"].get("fraction_samples_with_lock_wait")}


def summarize(rows, equivalence, output):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["variant"], row["workload"], row["users"])].append(row)
    aggregate = []
    for (variant, workload_name, users), group in sorted(groups.items()):
        for metric in AGGREGATE_METRICS:
            values = [row[metric] for row in group if row[metric] is not None]
            if values:
                aggregate.append({"variant": variant, "workload": workload_name, "users": users, "metric": metric,
                                  "trials": len(values), "median": median(values), "min": min(values),
                                  "max": max(values)})
    write_csv(output / "aggregate.csv", ("variant", "workload", "users", "metric", "trials", "median", "min", "max"),
              aggregate)
    index = {(row["variant"], row["workload"], row["users"], row["metric"]): row for row in aggregate}
    comparison = []
    for (variant, workload_name, users, metric), row in sorted(index.items()):
        if variant != "P1" or (key := ("C", workload_name, users, metric)) not in index:
            continue
        before, after = row["median"], index[key]["median"]
        comparison.append({"workload": workload_name, "users": users, "metric": metric, "trials": row["trials"],
                           "p1_median": before, "p1_min": row["min"], "p1_max": row["max"],
                           "c_median": after, "c_min": index[key]["min"], "c_max": index[key]["max"],
                           "change_pct": (after - before) / before * 100 if before else None,
                           "ranges_overlap": not (index[key]["max"] < row["min"] or index[key]["min"] > row["max"])})
    write_csv(output / "comparison.csv", ("workload", "users", "metric", "trials", "p1_median", "p1_min", "p1_max",
                                          "c_median", "c_min", "c_max", "change_pct", "ranges_overlap"), comparison)
    write_csv(output / "equivalence.csv", ("repetition", "workload", "users", "same_outcomes", "same_body_keys",
                                           "same_http_statuses"), equivalence)


# ---------------------------------------------------------------- main

def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    session = secrets.token_hex(4)
    base = f"busb_c_base_{session}"
    args.app_db_user = f"busb_c_app_{session}"
    password = secrets.token_urlsafe(30)
    pg_password = os.environ.get("PHASE2_PG_PASSWORD", "")

    def connect(db="postgres"):
        return psycopg.connect(host="127.0.0.1", port=args.pg_port, dbname=db, user="postgres",
                               password=pg_password, autocommit=True, row_factory=dict_row)

    environment = {**os.environ, "SPRING_PROFILES_ACTIVE": "dev", "SERVER_PORT": "8085",
                   "SERVER_ADDRESS": "127.0.0.1", "SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE": str(POOL),
                   "JWT_SECRET": base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
                   "EMAIL_OTP_SECRET": base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
                   "BOOTSTRAP_SUPER_ADMIN_ENABLED": "false", "SPRING_JPA_SHOW_SQL": "false"}
    environment.pop("PHASE2_PG_PASSWORD", None)
    java_version = subprocess.run([str(args.java), "-version"], capture_output=True, text=True, check=True).stderr.strip()
    cpuinfo = Path("/proc/cpuinfo")
    model = re.search(r"^model name\s*:\s*(.+)$", cpuinfo.read_text(), re.MULTILINE) if cpuinfo.is_file() else None
    manifest = {"start_utc": utc(), "platform": platform.platform(),
                "cpu_model": model[1] if model else platform.processor(), "cpu_logical": psutil.cpu_count(),
                "ram_bytes": psutil.virtual_memory().total, "jdk": java_version, "java_flags": JAVA_FLAGS,
                "hikari_max_pool": POOL, "python": platform.python_version(),
                "packages": {name: importlib.metadata.version(name)
                             for name in ("locust", "psutil", "psycopg", "requests")},
                "settings": {"seed": args.seed, "users": args.users, "workloads": args.workloads,
                             "max_in_flight": "equals users", "wait_seconds": 0, "repetitions": args.repetitions,
                             "idempotency_key": "not sent",
                             "fixture": {"legacy": [LEGACY_TRIPS, LEGACY_SEATS], "main": [MAIN_TRIPS, MAIN_SEATS],
                                         "warmup": [WARMUP_TRIPS, WARMUP_PER_TRIP]}},
                "source": {variant: {"source_sha": sha, "jar_name": jar.name, "jar_sha256": sha256(jar)}
                           for variant, sha, jar in (("P1", P1_SHA, args.p1_jar), ("C", args.c_sha, args.c_jar))},
                "note": "The C JAR also contains Phase 2B; without Idempotency-Key it runs the same create use case "
                        "as P1 except for the Phase 2C trip snapshot.",
                "input_sha256": {name: sha256(HERE / name) for name in ("benchmark.py", "locustfile.py", "fixture.sql")}}
    summary, equivalence, outcomes = [], [], {}
    with connect() as admin:
        manifest["postgresql"] = admin.execute("""
            SELECT name, setting, unit FROM pg_settings WHERE name IN (
                'server_version', 'default_transaction_isolation', 'shared_buffers', 'shared_preload_libraries',
                'max_connections', 'lock_timeout', 'statement_timeout', 'synchronous_commit',
                'pg_stat_statements.track')
            ORDER BY name
            """).fetchall()
        write_json(args.output / "manifest.json", manifest)
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
            sql.Identifier(args.app_db_user), sql.Literal(password)))
        try:
            admin.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(base), sql.Identifier(args.app_db_user)))
            # Build the clean P1 snapshot (V1-V16) with the P1 JAR, then load the fixture once.
            with backend(args, args.p1_jar, base, args.app_db_user, password,
                         args.output / "snapshot_backend.log", environment):
                pass
            with connect(base) as connection:
                if connection.execute("SELECT MAX(installed_rank) AS rank FROM flyway_schema_history").fetchone()["rank"] != 16:
                    raise RuntimeError("The P1 JAR must build the V1-V16 snapshot")
                connection.execute("CREATE EXTENSION pg_stat_statements")
                connection.execute("SET TIME ZONE 'UTC'")
                connection.execute((HERE / "fixture.sql").read_text(encoding="utf-8"))
                trips = connection.execute("""
                    SELECT t.id, t.available_seats, v.seat_capacity
                    FROM trips t JOIN vehicles v ON v.id = t.vehicle_id ORDER BY t.departure_time, t.id
                    """).fetchall()
                legacy, main = trips[:LEGACY_TRIPS], trips[LEGACY_TRIPS:LEGACY_TRIPS + MAIN_TRIPS]
                warmup = trips[LEGACY_TRIPS + MAIN_TRIPS:]
                if (len(warmup) != WARMUP_TRIPS or
                        any(row["available_seats"] != LEGACY_SEATS or row["seat_capacity"] != LEGACY_SEATS for row in legacy) or
                        any(row["available_seats"] != MAIN_SEATS or row["seat_capacity"] != MAIN_SEATS for row in main + warmup) or
                        connection.execute("SELECT count(*) AS n FROM bookings").fetchone()["n"]):
                    raise RuntimeError("The snapshot does not match the clean benchmark fixture")
            suites = workloads([row["id"] for row in legacy], [row["id"] for row in main],
                               [row["id"] for row in warmup], args.seed)
            paths = {name: args.output / f"intents_{name}.json" for name in suites}
            for name, path in paths.items():
                write_json(path, suites[name])
            manifest["intent_sha256"] = {name: sha256(path) for name, path in paths.items()}
            write_json(args.output / "manifest.json", manifest)

            for rep in range(1, args.repetitions + 1):
                order = ("P1", "C") if rep % 2 else ("C", "P1")
                for users in args.users:
                    for name in args.workloads:
                        for variant in order:
                            print(f"Run {rep}/{args.repetitions} | {users} users | {name} | {variant}", flush=True)
                            output = args.output / f"{rep:02d}_u{users:02d}_{name}_{variant}"
                            output.mkdir()
                            db = f"busb_c_run_{session}"
                            admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE {} OWNER {}").format(
                                sql.Identifier(db), sql.Identifier(base), sql.Identifier(args.app_db_user)))
                            try:
                                jar = args.p1_jar if variant == "P1" else args.c_jar
                                with backend(args, jar, db, args.app_db_user, password, output / "backend.log",
                                             environment) as java:
                                    metrics = run_trial(args, variant, users, name, suites[name], paths[name],
                                                        paths["warmup"], output, db, connect, java.pid)
                            finally:
                                admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(db)))
                            summary.append(flatten(metrics, rep))
                            write_csv(args.output / "summary.csv", SUMMARY_FIELDS, summary)
                            if not metrics["checked"]:
                                raise RuntimeError(f"Request and DB reconciliation failed: {output}")
                            outcomes[(rep, users, name, variant)] = metrics
                        p1, c = outcomes[(rep, users, name, "P1")], outcomes[(rep, users, name, "C")]
                        equivalence.append({"repetition": rep, "workload": name, "users": users,
                                            "same_outcomes": p1["outcome_sha256"] == c["outcome_sha256"],
                                            "same_body_keys": p1["body_keys"] == c["body_keys"],
                                            "same_http_statuses": p1["http_statuses"] == c["http_statuses"]})
                        if not all(list(equivalence[-1].values())[3:]):
                            raise RuntimeError(f"P1 and C responses differ: {equivalence[-1]}")
        finally:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(base)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(args.app_db_user)))
    write_json(args.output / "manifest.json", {**manifest, "end_utc": utc(), "completed_trials": len(summary)})
    summarize(summary, equivalence, args.output)


def parse_args():
    parser = argparse.ArgumentParser(description="BusBooking Phase 2C paired benchmark (P1 vs C)")
    for argument in ("java", "p1-jar", "c-jar", "output"):
        parser.add_argument(f"--{argument}", type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument("--c-sha", required=True)
    parser.add_argument("--pg-port", type=int, required=True)
    parser.add_argument("--pg-pid", type=int, required=True)
    parser.add_argument("--seed", type=int, default=20261126)
    parser.add_argument("--users", type=lambda value: [int(part) for part in value.split(",")], default=[10, 20])
    parser.add_argument("--workloads", type=lambda value: value.split(","), default=list(WORKLOADS))
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if any(users < 1 for users in args.users) or args.repetitions < 1:
        parser.error("Require at least one user and one repetition")
    if set(args.workloads) - set(WORKLOADS):
        parser.error(f"Workloads must be among {WORKLOADS}")
    if not re.fullmatch(r"[a-f0-9]{40}", args.c_sha) or args.c_sha == P1_SHA:
        parser.error("Pass the full, distinct Git SHA used to build the C JAR")
    if sha256(args.p1_jar) == sha256(args.c_jar):
        parser.error("P1 and C must be different JARs")
    return args


if __name__ == "__main__":
    run(parse_args())
