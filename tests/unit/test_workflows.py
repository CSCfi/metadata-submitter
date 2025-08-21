"""Test workflow schema."""

import unittest
from unittest.mock import patch

import ujson

from metadata_backend.conf.conf import API_PREFIX, WORKFLOWS, schema_types
from metadata_backend.helpers.schema_loader import JSONSchemaLoader
from metadata_backend.helpers.validator import JSONValidator
from metadata_backend.helpers.workflow import PublishServiceConfig, Workflow
from tests.unit.test_handlers import HandlersTestCase


class TestConfiguredWorkflows(unittest.TestCase):
    """Test configured workflow schemas."""

    def test_load_workflow_schema(self):
        """Test that the schema loader can open workflow schema."""
        workflow_schema = JSONSchemaLoader().get_schema("workflow")
        self.assertIs(type(workflow_schema), dict)

    def test_validate_workflows(self):
        """Test that the workflows can be validated."""
        for workflow in WORKFLOWS.values():
            JSONValidator(workflow.workflow, "workflow").validate()

    def test_required_schemas_exist(self):
        """Test that required schemas exist in the workflows."""
        schemas = set(schema_types.keys())

        for workflow in WORKFLOWS.values():
            workflow = workflow.workflow
            schemas_in_workflow = set()
            required_schemas = set()
            for step in workflow["steps"]:
                for schema in step["schemas"]:
                    # test that schema exists
                    self.assertIn(schema["name"], schemas)

                    # test that each schema shows up once in the workflow
                    self.assertNotIn(schema["name"], schemas_in_workflow)

                    schemas_in_workflow.add(schema["name"])
                    if "requires" in schema:
                        for item in schema["requires"]:
                            required_schemas.add(item)

            if "publish" in workflow:
                publishing = workflow["publish"]
                if "requiredSchemas" in publishing:
                    for item in publishing["requiredSchemas"]:
                        required_schemas.add(item)

            for required in required_schemas:
                self.assertIn(required, schemas)
                self.assertIn(required, schemas_in_workflow)


class TestWorkflow(HandlersTestCase):
    """Test workflow class."""

    WORKFLOWS_DIR = HandlersTestCase.TESTFILES_ROOT / "workflows"

    workflows = {}

    for workflow_name in {"valid"}:
        with open(WORKFLOWS_DIR / f"{workflow_name}.json", "rb") as workflow_file:

            workflows[workflow_name] = Workflow(ujson.load(workflow_file))

    valid_workflow = workflows["valid"]

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
