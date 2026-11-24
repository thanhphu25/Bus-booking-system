import csv, json, os, random
from locust import FastHttpUser, constant, events, task

PATHS = json.loads(os.environ['A_PATHS'])
RECORDS = []


@events.request.add_listener
def record(request_type, name, response_time, response_length, exception, **kwargs):
    RECORDS.append((name, round(response_time, 3), response_length, '' if exception is None else str(exception)[:200]))


@events.quitting.add_listener
def dump(environment, **kwargs):
    with open(os.environ['A_REQUESTS_CSV'], 'w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['name', 'response_ms', 'response_bytes', 'error'])
        writer.writerows(RECORDS)


class SearchUser(FastHttpUser):
    wait_time = constant(0)

    @task
    def search(self):
        name, path = random.choice(PATHS)
        with self.client.get(path, name=name, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f'HTTP {response.status_code}')
