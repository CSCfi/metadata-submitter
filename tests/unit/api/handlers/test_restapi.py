"""Test API endpoints from RESTAPIHandler."""

from unittest.mock import patch

import ujson

from metadata_backend.conf.conf import API_PREFIX
from metadata_backend.helpers.workflow import PublishServiceConfig, Workflow

from .common import HandlersTestCase


class RESTAPIHandlerTestCase(HandlersTestCase):
    """Schema API endpoint class test cases."""

    WORKFLOWS_DIR = HandlersTestCase.TESTFILES_ROOT / "workflows"

    workflows = {}

    for workflow_name in {"valid"}:
        with open(WORKFLOWS_DIR / f"{workflow_name}.json", "rb") as workflow_file:

            workflows[workflow_name] = Workflow(ujson.load(workflow_file))

    valid_workflow = workflows["valid"]

    async def test_correct_schema_types_are_returned(self):
        """Test API endpoint for all schema types."""
        with self.patch_verify_authorization:
            response = await self.client.get(f"{API_PREFIX}/schemas")
            response_text = await response.text()
            schema_titles = [
                "Submission",
                "Study",
                "Sample",
                "Experiment",
                "Run",
                "Analysis",
                "DAC",
                "Policy",
                "Dataset",
                "Project",
                "Datacite DOI schema",
                "Bigpicture Dataset",
                "Bigpicture Image",
                "Bigpicture Sample",
                "Bigpicture Staining",
                "Bigpicture Observation",
                "Bigpicture Observer",
                "Bigpicture REMS",
                "Bigpicture Organisation",
                "Bigpicture Policy",
                "Bigpicture Landing page",
            ]

            for title in schema_titles:
                self.assertIn(title, response_text)

    async def test_correct_study_schema_are_returned(self):
        """Test API endpoint for study schema types."""
        with self.patch_verify_authorization:
            response = await self.client.get(f"{API_PREFIX}/schemas/study")
            response_text = await response.text()
            self.assertIn("study", response_text)
            self.assertNotIn("submission", response_text)

    async def test_raises_invalid_schema(self):
        """Test API endpoint for study schema types."""
        with self.patch_verify_authorization:
            response = await self.client.get(f"{API_PREFIX}/schemas/something")
            self.assertEqual(response.status, 404)

    async def test_raises_not_found_schema(self):
        """Test API endpoint for study schema types."""
        with self.patch_verify_authorization:
            response = await self.client.get(f"{API_PREFIX}/schemas/project")
            self.assertEqual(response.status, 400)
            resp_json = await response.json()
            self.assertEqual(
                resp_json["detail"], "The provided schema type could not be found. Occurred for JSON schema: 'project'."
            )

    async def test_get_schema_submission(self):
        """Test API endpoint for submission schema type."""
        with self.patch_verify_authorization:
            response = await self.client.get(f"{API_PREFIX}/schemas/submission")
            self.assertEqual(response.status, 200)
            resp_json = await response.json()
            assert resp_json["$schema"] == "https://json-schema.org/draft/2020-12/schema"
            assert resp_json["description"] == "Submission that contains submitted metadata objects"

    def test_validate_workflows(self):
        """Test validate workflow."""
        self.valid_workflow.validate()

    def test_properties(self):
        """Test Workflow properties."""
        workflow = self.workflows["valid"]
        assert workflow.single_instance_schemas == {"dataset"}
        assert workflow.required_schemas == {"dataset"}
        assert workflow.schemas == {"dataset"}
        assert workflow.publish_config.datacite_config == PublishServiceConfig(service="csc", schemas=["dataset"])
        assert workflow.publish_config.rems_config == PublishServiceConfig(service="csc", schemas=["dataset"])
        assert workflow.publish_config.discovery_config == PublishServiceConfig(service="metax", schemas=["dataset"])

    async def test_workflow_endpoints(self):
        """Test workflow endpoints."""
        with (
            patch.dict("metadata_backend.conf.conf.WORKFLOWS", self.workflows, clear=True),
            self.patch_verify_authorization,
        ):
            async with self.client.get(f"{API_PREFIX}/workflows") as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.content_type, "application/json")
                workflows = await response.json()
                self.assertEqual(workflows, {"valid": ""})

            for workflow_name in workflows.keys():
                async with self.client.get(f"{API_PREFIX}/workflows/{workflow_name}") as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.content_type, "application/json")
                    workflow = await response.json()
                    self.assertEqual(workflow["name"], workflow_name)

            with self.assertRaises(Exception):
                async with self.client.get(f"{API_PREFIX}/workflows/notfound") as response:
                    self.assertEqual(response.status, 404)
                    self.assertEqual(response.content_type, "application/json")
