import time
from locust import HttpUser, task, between

class QuickstartUser(HttpUser):
    wait_time = between(1, 2.5)

    @task
    def post_new_folder(self):
        self.client.post("/folders", json={"name": "test", "description": "test description"})

    def on_start(self):
        self.client.get("/aai")
