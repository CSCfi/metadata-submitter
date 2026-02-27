"""NBIS deployment performance test."""

from pathlib import Path

from locust import HttpUser, between, task

from metadata_backend.api.models.submission import Submission
from metadata_backend.conf.conf import API_PREFIX
from tests.utils import bp_submission_documents, bp_update_documents

TEST_FILES_ROOT = Path(__file__).parent.parent / "test_files"

# locust -f locustfile_nbis.py -u 2


class NbisDeployment(HttpUser):
    abstract = True
    task_name = None  # Override in subclass instance
    is_datacite = None  # Override in subclass instance

    host = "http://localhost:5431"

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

    def _submit_no_publish(self):
        """Create submission without publishing."""

        is_datacite = True

        # Create new submission
        submission_name, object_names, files = bp_submission_documents(is_datacite=is_datacite)
        with self.client.post(
            f"{API_PREFIX}/submit",
            files={name: (name, file) for name, file in files.items()},
            catch_response=True,
            name=f"{self.task_name} {API_PREFIX}/submit",
        ) as resp:
            if resp.status_code != 200:
                self.report_failure(resp, "Submission creation")
            submission_id = resp.json()["submissionId"]

        # Create another submission with the same submission name
        _, _, files = bp_submission_documents(is_datacite=is_datacite, submission_name=submission_name)
        with self.client.post(
            f"{API_PREFIX}/submit",
            files={name: (name, file) for name, file in files.items()},
            catch_response=True,
            name=f"{self.task_name} {API_PREFIX}/submit [same name]",
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
            _, _, files = bp_update_documents(submission_name, object_names, is_datacite=is_datacite)
            with self.client.patch(
                f"{API_PREFIX}/submit/{submission_id}",
                files={name: (name, file) for name, file in files.items()},
                catch_response=True,
                name=f"{self.task_name} {API_PREFIX}/submit [update]",
            ) as resp:
                if resp.status_code != 200:
                    print(resp.json())
                    self.report_failure(resp, "Submission update")

    pass


class NbisDeploymentWithDatacite(NbisDeployment):
    def on_start(self):
        self.is_datacite = True
        self.task_name = "[nbis with datacite - no publish]"
        super().on_start()

    @task
    def submit_no_publish(self):
        super()._submit_no_publish()


class NbisDeploymentWithoutDatacite(NbisDeployment):
    def on_start(self):
        self.is_datacite = False
        self.task_name = "[nbis without datacite - no publish]"
        super().on_start()

    @task
    def submit_no_publish(self):
        super()._submit_no_publish()
