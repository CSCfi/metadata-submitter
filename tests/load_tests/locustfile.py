import time
import json

from pathlib import Path
from locust import HttpUser, task, tag, between

testfiles_root = Path(__file__).parent.parent / "test_files"
path_to_file = testfiles_root / "study" / "SRP000539.json"
path = path_to_file.as_posix()
with open(path, "r") as file:
    json_file = file.read()

class BasicUser(HttpUser):
    wait_time = between(1, 5)

    @tag('post')
    @task
    def post_objects(self):
        with self.client.post("/objects/study", json=json.loads(json_file), catch_response=True) as response:
            if response.status_code != 201:
                response.failure("Object was not added successfully.")

    @tag('query')
    @task
    def query_objects(self):
        with self.client.get("/objects/study?studyAttributes=find_this", catch_response=True) as response:
            if response.json()["page"]["totalObjects"] != 1:
                response.failure("Query returned more objects than it should.")

    def on_start(self):
        # Login
        self.client.get("/aai")
