"""Run load tests for submitting folders and objects and querying them."""

import json

from pathlib import Path
from locust import HttpUser, task, tag, between

testfiles_root = Path(__file__).parent / "test_files"


class BasicUser(HttpUser):
    """API load test cases."""

    wait_time = between(1, 3)

    def on_start(self):
        """Login the user at the start of the test."""
        with self.client.get("/aai", catch_response=True) as resp:
            # Response is 404 if frontend is not running but login is still successful
            if resp.status_code == 404:
                resp.success()

    @tag("post")
    @task
    def post_folder1(self):
        """Create a folder with one object."""

        # Get a test JSON object
        json_file = self.get_json_object("study", "SRP000539.json")

        # Create new folder
        test_folder = {"name": "test1", "description": "test folder"}
        with self.client.post("/folders", json=test_folder, catch_response=True) as resp:
            if resp.status_code != 201:
                resp.failure("Folder was not added successfully.")
            folder_id = resp.json()["folderId"]

        # Post a study object
        with self.client.post("/objects/study", json=json_file, catch_response=True) as resp:
            if resp.status_code != 201:
                resp.failure("Object was not added successfully.")
            accession_id = resp.json()["accessionId"]

        # Patch the object into the previously created folder
        patch_object = [
            {"op": "add", "path": "/metadataObjects/-", "value": {"accessionId": accession_id, "schema": "study"}}
        ]
        with self.client.patch(
            f"/folders/{folder_id}", json=patch_object, name="/folders/{folderId}", catch_response=True
        ) as resp:
            if resp.status_code != 200:
                resp.failure("Object was not patched to folder successfully.")

    @tag("post")
    @task
    def post_folder2(self):
        """Create a folder with two objects."""

        # Get test JSON objects
        json_file1 = self.get_json_object("study", "SRP000539.json")
        json_file2 = self.get_json_object("experiment", "ERX000119.json")

        # Create new folder
        test_folder = {"name": "test2", "description": "another test folder"}
        with self.client.post("/folders", json=test_folder, catch_response=True) as resp:
            if resp.status_code != 201:
                resp.failure("Folder was not added successfully.")
            folder_id = resp.json()["folderId"]

        # Post a study object
        with self.client.post("/objects/study", json=json_file1, catch_response=True) as resp:
            if resp.status_code != 201:
                resp.failure("Object was not added successfully.")
            accession_id1 = resp.json()["accessionId"]

        # Patch the study into the folder
        patch_object1 = [
            {"op": "add", "path": "/metadataObjects/-", "value": {"accessionId": accession_id1, "schema": "study"}}
        ]
        with self.client.patch(
            f"/folders/{folder_id}", json=patch_object1, name="/folders/{folderId}", catch_response=True
        ) as resp:
            if resp.status_code != 200:
                resp.failure("Object was not patched to folder successfully.")

        # Post an experiment object
        with self.client.post("/objects/experiment", json=json_file2, catch_response=True) as resp:
            if resp.status_code != 201:
                resp.failure("Object was not added successfully.")
            accession_id2 = resp.json()["accessionId"]

        # Patch the experiment object into the folder
        patch_object2 = [
            {"op": "add", "path": "/metadataObjects/-", "value": {"accessionId": accession_id2, "schema": "experiment"}}
        ]
        with self.client.patch(
            f"/folders/{folder_id}", json=patch_object2, name="/folders/{folderId}", catch_response=True
        ) as resp:
            if resp.status_code != 200:
                resp.failure("Object was not patched to folder successfully.")

    def get_json_object(self, schema, file_name):
        """Return a JSON object from a test file."""
        path_to_file = testfiles_root / schema / file_name
        path = path_to_file.as_posix()
        with open(path, "r") as file:
            json_file = file.read()
        return json.loads(json_file)

    @tag("query")
    @task
    def get_folders_and_objects(self):
        """Get users folders, read one of the objects in a folder and get the object by accession ID."""

        with self.client.get("/folders", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure("Getting folders was unsuccesful.")
            elif resp.json()["page"]["totalFolders"] == 0:
                resp.failure("Query returned 0 folders.")
            # Get some values from the folder response
            obj_acc_id = resp.json()["folders"][0]["metadataObjects"][0]["accessionId"]
            obj_schema = resp.json()["folders"][0]["metadataObjects"][0]["schema"]

        with self.client.get(
            f"/objects/{obj_schema}/{obj_acc_id}", name = "/objects/{schema}/{accessionId}", catch_response=True
        ) as resp:
            if resp.status_code != 200:
                resp.failure("Getting an object was unsuccesful.")
