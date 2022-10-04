"""Test workflow schema."""
import unittest
from unittest.mock import patch

import ujson

from metadata_backend.conf.conf import API_PREFIX, WORKFLOWS, schema_types
from metadata_backend.helpers.schema_loader import JSONSchemaLoader
from metadata_backend.helpers.validator import JSONValidator
from metadata_backend.helpers.workflow import Workflow
from tests.unit.test_handlers import HandlersTestCase


class TestWorkflowSchema(unittest.TestCase):
    """Test workflow schema."""

    def test_workflow_schema_loader(self):
        """Test that the schema loader can open workflow schema."""
        workflow_schema = JSONSchemaLoader().get_schema("workflow")
        self.assertIs(type(workflow_schema), dict)

    def test_validate_workflows(self):
        """Test that the workflows can be validated."""
        for workflow in WORKFLOWS.values():
            JSONValidator(workflow.workflow, "workflow").validate

    def test_referenced_schemas_exist(self):
        """Test that referenced schemas in the workflows exist."""
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
                    if "requires_or" in schema:
                        for item in schema["requires_or"]:
                            required_schemas.add(item)

            if "publish" in workflow:
                for publish in workflow["publish"]:
                    if "requiredSchemas" in publish:
                        for item in publish["requiredSchemas"]:
                            required_schemas.add(item)

            for required in required_schemas:
                self.assertIn(required, schemas)
                self.assertIn(required, schemas_in_workflow)


class TestWorkflow(HandlersTestCase):
    """Test Workflow class and endpoints."""

    path_to_workflows = HandlersTestCase.TESTFILES_ROOT / "workflows"

    WORKFLOWS_DICT = {}
    WORKFLOWS = {}

    for workflow_name in {"valid", "invalid"}:
        with open(path_to_workflows / f"{workflow_name}.json", "rb") as workflow_file:
            workflow_dict = ujson.load(workflow_file)
            WORKFLOWS_DICT[workflow_name] = workflow_dict
            WORKFLOWS[workflow_name] = Workflow(workflow_dict)

    def test_validate_workflows(self):
        """Test workflows validate or fail to."""
        workflow_valid = self.WORKFLOWS["valid"]
        self.assertTrue(workflow_valid.validate())
        self.assertEqual(workflow_valid.workflow, self.WORKFLOWS_DICT["valid"])

        workflow_invalid = self.WORKFLOWS["invalid"]
        self.assertFalse(workflow_invalid.validate())

    def test_single_properties(self):
        """Test Workflow properties."""
        workflow = self.WORKFLOWS["valid"]
        self.assertEqual(workflow.single_instance_schemas, {"study", "bpdataset"})
        self.assertEqual(workflow.required_schemas, {"study", "dac", "image", "bpdataset"})
        schemas_in_workflow = {"study", "dac", "policy", "image", "bpdataset", "experiment", "run"}
        self.assertEqual(workflow.schemas, schemas_in_workflow)
        self.assertEqual(set(workflow.schemas_dict.keys()), schemas_in_workflow)
        self.assertEqual(workflow.schemas, set(workflow.schemas_dict.keys()))
        self.assertEqual(workflow.endpoints, {"datacite"})

    async def test_workflow_endpoints(self):
        """Test workflow endpoints."""
        with patch.dict("metadata_backend.conf.conf.WORKFLOWS", self.WORKFLOWS, clear=True), self.p_get_sess_restapi:
            async with self.client.get(f"{API_PREFIX}/workflows") as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.content_type, "application/json")
                workflows = await response.json()
                self.assertEqual(workflows, {"valid": "", "invalid": ""})

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


if __name__ == "__main__":
    unittest.main()
