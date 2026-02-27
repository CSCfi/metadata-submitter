"""CSC deployment performance test."""

import json
import uuid
from pathlib import Path

from locust import HttpUser, between, task

from metadata_backend.api.json import to_json_dict
from metadata_backend.api.models.submission import Submission
from metadata_backend.conf.conf import API_PREFIX

TEST_FILES_ROOT = Path(__file__).parent.parent / "test_files"

# locust -f locustfile_csc.py


class CscDeployment(HttpUser):
    host = "http://localhost:5430"

    task_name = "[csc - no publish]"

    def on_start(self):
        """Login the user at the start of the test."""

        # Start login
        resp = self.client.get("/login", allow_redirects=False, name=f"{self.task_name} /login")
        if resp.status_code not in (302, 303):
            raise Exception("Login failed")
        redirect = resp.headers["Location"]

        # Follow redirect to /authorize
        resp = self.client.get(redirect, allow_redirects=False, name=f"{self.task_name} redirect to /authorize")
        if resp.status_code not in (302, 303):
            raise Exception("Authorize failed")
        redirect = resp.headers["Location"]

        # Follow redirect to /callback
        resp = self.client.get(redirect, allow_redirects=False, name=f"{self.task_name} redirect to /callback")
        if resp.status_code not in (302, 303):
            raise Exception("Callback failed")

        access_token = resp.cookies.get("access_token")
        if not access_token:
            raise Exception("Missing access token")

        # Store access token in user session
        self.client.cookies.set("access_token", access_token)

    wait_time = between(1, 3)

    @staticmethod
    def report_failure(resp, test: str):
        data = resp.json()
        if "detail" in data:
            resp.failure(f"{test} failed with code {resp.status_code}: {data['detail']}.")
        else:
            resp.failure(f"{test} failed with code {resp.status_code}.")

    @task
    def submit_no_publish(self):
        """Create submission without publishing."""

        # Get the test submission document
        submission = self.read_sd_submission()

        # Create new submission
        with self.client.post(
            f"{API_PREFIX}/submissions",
            json=to_json_dict(submission),
            catch_response=True,
            name=f"{self.task_name} {API_PREFIX}/submissions",
        ) as resp:
            if resp.status_code != 201:
                self.report_failure(resp, "Submission creation")
            submission_id = resp.json()["submissionId"]

        # Create another submission with the same name fails
        with self.client.post(
            f"{API_PREFIX}/submissions",
            json=to_json_dict(submission),
            catch_response=True,
            name=f"{self.task_name} {API_PREFIX}/submissions [same name]",
        ) as resp:
            if resp.status_code == 400:
                resp.success()
            else:
                self.report_failure(resp, "Submission creation [same name]")

        # Get submission
        with self.client.get(
            f"{API_PREFIX}/submissions/{submission_id}",
            catch_response=True,
            name=f"{self.task_name} {API_PREFIX}/submissions [new]",
        ) as resp:
            if resp.status_code != 200:
                self.report_failure(resp, "Get submission [new]")

            data = resp.json()
            try:
                Submission.model_validate(data)
            except Exception:
                self.report_failure(resp, "Get submission body [new]")

        # Update submission
        submission.title = f"name_{uuid.uuid4()}"
        with self.client.patch(
            f"{API_PREFIX}/submissions/{submission_id}",
            json=to_json_dict(submission),
            catch_response=True,
            name=f"{self.task_name} {API_PREFIX}/submissions [update]",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                self.report_failure(resp, "Submission update")

        # Get submission
        with self.client.get(
            f"{API_PREFIX}/submissions/{submission_id}",
            catch_response=True,
            name=f"{self.task_name} {API_PREFIX}/submissions [update]",
        ) as resp:
            if resp.status_code != 200:
                self.report_failure(resp, "Get submission [update]")
            data = resp.json()
            try:
                update_submission = Submission.model_validate(data)
            except Exception:
                self.report_failure(resp, "Get submission body [update]")
            if update_submission.title != submission.title:
                self.report_failure(resp, "Get submission title [update]")

    @staticmethod
    def read_sd_submission() -> Submission:
        """Return a SD submission document with a unique name."""

        path = TEST_FILES_ROOT / "submission" / "submission.json"
        with open(path, "r") as file:
            data = json.load(file)
            data["projectId"] = "1000"
            data["name"] = f"test_{uuid.uuid4()}"
            submission = Submission.model_validate(data)
            return submission
