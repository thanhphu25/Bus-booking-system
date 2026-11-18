import csv
import json
import os
import time
from collections import deque
from pathlib import Path

import gevent
from gevent.lock import BoundedSemaphore, Semaphore
from locust import FastHttpUser, events, task
from locust.exception import StopUser


fields = (
    "intent_id", "mode", "attempt", "started_ns", "duration_ms", "status", "booking_id",
    "error", "response_bytes",
)


@events.init.add_listener
def configure(environment, **kwargs):
    suite = json.loads(Path(os.environ["BOOKING_SUITE"]).read_text(encoding="utf-8"))
    environment.booking_jobs = deque(suite)
    environment.booking_remaining = len(suite)
    environment.booking_tokens = json.loads(os.environ["BOOKING_TOKENS"])
    environment.booking_limit = BoundedSemaphore(environment.parsed_options.num_users)
    environment.booking_pair_lock = Semaphore()
    environment.booking_requests = []


@events.test_start.add_listener
def record_start(environment, **kwargs):
    environment.booking_started = time.monotonic_ns()


@events.quitting.add_listener
def export(environment, **kwargs):
    prefix = Path(os.environ["BOOKING_OUTPUT"])
    with prefix.with_suffix(".csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(environment.booking_requests)
    prefix.with_suffix(".json").write_text(json.dumps({
        "start_ns": getattr(environment, "booking_started", None),
        "end_ns": getattr(environment, "booking_ended", None),
        "unfinished_jobs": environment.booking_remaining,
    }), encoding="utf-8")


class BookingUser(FastHttpUser):
    connection_timeout = 5
    network_timeout = 30

    def send_booking(self, job, attempt):
        started = time.monotonic_ns()
        with self.client.post(
            "/api/bookings", json=job["payload"], catch_response=True, name=f"booking/{attempt}",
            headers={"Authorization": f"Bearer {self.environment.booking_tokens[job['user']]}",
                     "Idempotency-Key": job["key"]},
        ) as response:
            elapsed = (time.monotonic_ns() - started) / 1_000_000
            try:
                body = response.json()
            except (ValueError, TypeError):
                body = {}
            if not isinstance(body, dict):
                body = {}
            code = response.status_code or 0
            booking_id = body.get("id") if code in (200, 201) else None
            error = ""
            if booking_id is None:
                error = body.get("error") or ("TRANSPORT_ERROR" if not code else f"HTTP_{code}")
                response.failure(error)
            self.environment.booking_requests.append(dict(
                intent_id=job["intent_id"], mode=job["mode"], attempt=attempt,
                started_ns=started, duration_ms=elapsed, status=code,
                booking_id=booking_id, error=error, response_bytes=len(response.content or b""),
            ))

    @task
    def next_intent(self):
        if not self.environment.booking_jobs:
            raise StopUser()
        job = self.environment.booking_jobs.popleft()
        limit = self.environment.booking_limit
        if job["mode"] == "concurrent":
            # Reserve both slots before dispatch so the pair can overlap under the shared cap.
            with self.environment.booking_pair_lock:
                limit.acquire()
                limit.acquire()
            try:
                first = gevent.spawn(self.send_booking, job, "first")
                replay = gevent.spawn(self.send_booking, job, "retry")
                gevent.joinall([first, replay], raise_error=True)
            finally:
                limit.release()
                limit.release()
        else:
            with limit:
                self.send_booking(job, "first")
                if job["mode"] == "sequential":
                    self.send_booking(job, "retry")
        self.environment.booking_remaining -= 1
        if self.environment.booking_remaining == 0:
            self.environment.booking_ended = time.monotonic_ns()
            gevent.spawn(self.environment.runner.quit)
