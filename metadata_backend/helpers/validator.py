"""Utility classes for validating XML or JSON files."""

from typing import Any

from jsonschema import Draft202012Validator, validators
from jsonschema.exceptions import ValidationError
from jsonschema.protocols import Validator

from ..api.exceptions import UserException
from .logger import LOG
from .schema_loader import JSONSchemaLoader, SchemaFileNotFoundException


def extend_with_default(validator_class: Draft202012Validator) -> Draft202012Validator:
    """Include default values present in JSON Schema.

    This feature is included even though some default values might cause
    unwanted behaviour when submitting a schema.

    Source: https://python-jsonschema.readthedocs.io FAQ
    """
    validate_properties = validator_class.VALIDATORS["properties"]

    def set_defaults(
        validator: Draft202012Validator, properties: dict[str, Any], instance: Draft202012Validator, schema: str
    ) -> Validator:
        for prop, subschema in properties.items():
            if "default" in subschema:
                instance.setdefault(prop, subschema["default"])

        yield from validate_properties(validator, properties, instance, schema)

    return validators.extend(
        validator_class,
        {"properties": set_defaults},
    )


DefaultValidatingDraft202012Validator = extend_with_default(Draft202012Validator)


class JSONValidator:
    """JSON Validator implementation."""

    def __init__(self, json_data: dict[str, Any], schema_type: str) -> None:
        """Set variables.

        :param json_data: JSON content to be validated
        :param schema_type: Schema type to be used for validation
        """
        self.json_data = json_data
        self.schema_type = schema_type

    def validate(self) -> None:
        """Check validation against JSON schema.

        :raises: HTTPBadRequest if validation fails.
        """
        try:
            schema = JSONSchemaLoader().get_schema(self.schema_type)
            LOG.info("Validated against JSON schema.")
            DefaultValidatingDraft202012Validator(schema).validate(self.json_data)
        except SchemaFileNotFoundException as e:
            reason = f"{e} ({self.schema_type})"
            LOG.exception(reason)
            raise UserException(reason) from e
        except ValidationError as e:
            if len(e.path) > 0:
                field = e.path[-1] if not isinstance(e.path[-1], int) else e.path[-2]
                reason = f"Provided input does not seem correct for field: '{field}'"
                LOG.debug("Provided JSON input: '%r'", e.instance)
                LOG.exception(reason)
                raise UserException(reason) from e

            reason = f"Provided input does not seem correct because: '{e.message}'"
            LOG.debug("Provided JSON input: '%r'", e.instance)
            LOG.exception(reason)
            raise UserException(reason) from e
