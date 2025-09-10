"""Test workflow schema."""

import unittest

from metadata_backend.conf.conf import WORKFLOWS, schema_types
from metadata_backend.helpers.schema_loader import JSONSchemaLoader
from metadata_backend.helpers.validator import JSONValidator


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
