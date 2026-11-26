import csv
import json
import os
import time
from collections import deque
from pathlib import Path

import gevent
from gevent.lock import BoundedSemaphore
from locust import FastHttpUser, events, task
from locust.exception import StopUser


fields = ("intent_id", "trip_id", "started_ns", "duration_ms", "status", "booking_id", "error",
          "response_bytes", "body_keys")


@events.init.add_listener
def configure(environment, **kwargs):
    suite = json.loads(Path(os.environ["BOOKING_SUITE"]).read_text(encoding="utf-8"))
    environment.booking_jobs = deque(suite)
    environment.booking_remaining = len(suite)
    environment.booking_tokens = json.loads(os.environ["BOOKING_TOKENS"])
    # Caps requests in flight at the number of Locust users; jobs are taken strictly in list order.
    environment.booking_limit = BoundedSemaphore(environment.parsed_options.num_users)
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
    # No think time: the comparison is a controlled closed-loop load, not a capacity test.
    connection_timeout = 5
    network_timeout = 30

    @task
    def next_intent(self):
        if not self.environment.booking_jobs:
            raise StopUser()
        job = self.environment.booking_jobs.popleft()
        with self.environment.booking_limit:
            started = time.monotonic_ns()
            # No Idempotency-Key: P1 and C must run the same create path.
            with self.client.post(
                "/api/bookings", json=job["payload"], catch_response=True, name="booking",
                headers={"Authorization": f"Bearer {self.environment.booking_tokens[job['user']]}"},
            ) as response:
                elapsed = (time.monotonic_ns() - started) / 1_000_000
                try:
                    body = response.json()
                except (ValueError, TypeError):
                    body = {}
                if not isinstance(body, dict):
                    body = {}
                code = response.status_code or 0
                booking_id = body.get("id") if code == 201 else None
                error = ""
                if booking_id is None:
                    error = body.get("error") or ("TRANSPORT_ERROR" if not code else f"HTTP_{code}")
                    response.failure(error)
                self.environment.booking_requests.append(dict(
                    intent_id=job["intent_id"], trip_id=job["payload"]["tripId"], started_ns=started,
                    duration_ms=elapsed, status=code, booking_id=booking_id, error=error,
                    response_bytes=len(response.content or b""), body_keys=",".join(sorted(body)),
                ))
        self.environment.booking_remaining -= 1
        if self.environment.booking_remaining == 0:
            self.environment.booking_ended = time.monotonic_ns()
            gevent.spawn(self.environment.runner.quit)
