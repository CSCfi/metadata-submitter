"""Utilities for processing a workflow."""

from typing import Any, Set

from aiohttp import web

from .validator import JSONValidator


class Workflow:
    """Submission workflow."""

    def __init__(self, workflow: dict[str, Any]) -> None:
        """Submission workflow.

        :param workflow: Workflow data
        """
        self._workflow = workflow
        self.name = workflow["name"]
        self.description = workflow["description"]

    def validate(self) -> bool:
        """Validate workflow against its schema."""
        try:
            JSONValidator(self._workflow, "workflow").validate
            return True
        except web.HTTPException:
            return False

    @property
    def workflow(self) -> dict[str, Any]:
        """Return workflow, no set method, only get."""
        return self._workflow

    @property
    def schemas(self) -> Set[str]:
        """Get all workflow schemas."""
        schemas_in_workflow = set()

        for step in self._workflow["steps"]:
            for schema in step["schemas"]:
                schemas_in_workflow.add(schema["name"])

        return schemas_in_workflow

    @property
    def schemas_dict(self) -> dict[str, Any]:
        """Get all workflow schemas as a dictionary, schema name as key."""
        schemas_dict = {}

        for step in self._workflow["steps"]:
            for schema in step["schemas"]:
                schemas_dict[schema["name"]] = schema

        return schemas_dict

    @property
    def required_schemas(self) -> Set[str]:
        """Get all required schemas.

        Required schemas are marked with their `required` field.
        Schemas referenced in a `requires` field are also marked as required.
        Step being required or not does not affect the requirements, it's for use in the front-end only.
        Schemas referenced in the `publish` or `announce` field under `requiredSchemas` are also marked as required.
        """
        required_schemas = set()

        for step in self._workflow["steps"]:
            for schema in step["schemas"]:
                if schema.get("required", False):
                    required_schemas.add(schema["name"])
                    if "requires" in schema:
                        for item in schema["requires"]:
                            required_schemas.add(item)

        if ("publish" or "announce") in self._workflow:
            publishing = self._workflow["publish"] if "publish" in self._workflow else self._workflow["announce"]
            if "requiredSchemas" in publishing:
                for item in publishing["requiredSchemas"]:
                    required_schemas.add(item)

        return required_schemas

    @property
    def single_instance_schemas(self) -> Set[str]:
        """Get workflow schemas that don't allow multiple objects."""
        single_instance = set()

        for step in self._workflow["steps"]:
            for schema in step["schemas"]:
                if not schema.get("allowMultipleObjects", True):
                    single_instance.add(schema["name"])

        return single_instance

    @property
    def endpoints(self) -> Set[str]:
        """Get endpoint names that the submission should be published to."""
        publishing = self._workflow["publish"] if "publish" in self._workflow else self._workflow["announce"]
        return {publish["name"] for publish in publishing}

    def get_endpoint_conf(self, name: str, value: str) -> str:
        """Get endpoint config value for a particular publishing endpoint."""
        publishing = self._workflow["publish"] if "publish" in self._workflow else self._workflow["announce"]
        conf: str = next(publish[value] for publish in publishing if publish["name"] == name)
        return conf
