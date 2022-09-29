"""Test workflow schema."""
import unittest

from metadata_backend.conf.conf import WORKFLOWS, schema_types
from metadata_backend.helpers.schema_loader import JSONSchemaLoader
from metadata_backend.helpers.validator import JSONValidator


class TestWorkflowSchema(unittest.TestCase):
    """Test workflow schema."""

    def test_workflow_schema_loader(self):
        """Test that the schema loader can open workflow schema."""
        workflow_schema = JSONSchemaLoader().get_schema("workflow")
        self.assertIs(type(workflow_schema), dict)

    def test_validate_workflows(self):
        """Test that the workflows can be validated."""
        for workflow in WORKFLOWS.values():
            JSONValidator(workflow, "workflow").validate

    def test_referenced_schemas_exist(self):
        """Test that referenced schemas in the workflows exist."""
        schemas = set(schema_types.keys())
        schemas_in_workflow = set()
        required_schemas = set()

        for workflow in WORKFLOWS.values():
            for step in workflow["steps"]:
                for schema in step["schemas"]:
                    self.assertIn(schema["name"], schemas)

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


if __name__ == "__main__":
    unittest.main()
