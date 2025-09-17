"""Utilities for processing a workflow."""

from typing import Any, ClassVar, Set

from pydantic import BaseModel, ConfigDict, Field

from ..api.exceptions import SystemException
from .validator import JSONValidator


class PublishServiceConfig(BaseModel):
    """Service configuration."""

    service: str
    submission: bool = False
    schemas: list[str] = Field(default_factory=list)  # Metadata object types.


class PublishConfig(BaseModel):
    """Publish service configuration."""

    model_config: ClassVar[ConfigDict] = {
        "populate_by_name": True,
        "populate_by_alias": True,  # type: ignore
    }

    datacite_config: PublishServiceConfig = Field(..., alias="datacite")
    rems_config: PublishServiceConfig = Field(..., alias="rems")
    discovery_config: PublishServiceConfig = Field(..., alias="discovery")


class Workflow:
    """Submission workflow configuration."""

    def __init__(self, workflow: dict[str, Any]) -> None:
        """Submission workflow configuration.

        :param workflow: Workflow data
        """
        self._workflow = workflow
        self.name = workflow["name"]
        self.description = workflow["description"]

    def validate(self) -> None:
        """Validate workflow against its schema."""

        JSONValidator(self._workflow, "workflow").validate()

        publish_config = self.publish_config
        datacite_config: PublishServiceConfig = publish_config.datacite_config
        rems_config: PublishServiceConfig = publish_config.rems_config
        discovery_config: PublishServiceConfig = publish_config.discovery_config

        missing = set(rems_config.schemas) - set(datacite_config.schemas)  # pylint: disable=no-member
        if missing:
            raise SystemException(
                f"REMS metadata object requires DOI from DataCite for schemas: {missing} in workflow: {Workflow}"
            )

        missing = set(discovery_config.schemas) - set(datacite_config.schemas)  # pylint: disable=no-member
        if missing:
            raise SystemException(
                f"Discovery metadata object requires DOI from DataCite for schemas: {missing} in workflow: {Workflow}"
            )

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
    def publish_config(self) -> PublishConfig:
        """Get publish service configuration."""
        if "publish" in self._workflow:
            return PublishConfig(**self._workflow["publish"])

        raise SystemException(f"Missing 'publish' configuration for workflow: {self._workflow}")
