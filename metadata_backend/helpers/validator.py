"""Utility classes for validating XML or JSON files."""

import re
from io import StringIO
from typing import Dict
from urllib.error import URLError

import ujson
from aiohttp import web
from defusedxml.ElementTree import ParseError
from defusedxml.ElementTree import tostring as etree_tostring
from jsonschema import Draft202012Validator, validators
from jsonschema.exceptions import ValidationError
from jsonschema.protocols import Validator
from xmlschema import XMLSchema, XMLSchemaValidationError

from ..helpers.logger import LOG
from .schema_loader import JSONSchemaLoader, SchemaNotFoundException


class XMLValidator:
    """XML Validator implementation."""

    def __init__(self, schema: XMLSchema, xml: str) -> None:
        """Set variables.

        :param schema: Schema to be used
        :param xml: Content of XML file to be validated
        """
        self.schema = schema
        self.xml_content = xml

    @property
    def resp_body(self) -> str:
        """Check validation and organize validation error details.

        :returns: JSON formatted string that provides details of validation
        :raises: HTTPBadRequest if URLError was raised during validation
        """
        try:
            self.schema.validate(self.xml_content)
            LOG.info("Submitted file is totally valid.")
            return ujson.dumps({"isValid": True})

        except ParseError as error:
            reason = self._parse_error_reason(error)
            # Manually find instance element
            lines = StringIO(self.xml_content).readlines()
            line = lines[error.position[0] - 1]  # line of instance
            instance = re.sub(r"^.*?<", "<", line)  # strip whitespaces

            LOG.info("Submitted file does not not contain valid XML syntax.")
            return ujson.dumps({"isValid": False, "detail": {"reason": reason, "instance": instance}})

        except XMLSchemaValidationError as error:
            # Parse reason and instance from the validation error message
            reason = str(error.reason)
            response: Dict = {"isValid": False, "detail": {"reason": reason}}
            if error.elem:
                instance = etree_tostring(error.elem, encoding="unicode")
                # Replace element address in reason with instance element
                if "<" in reason and ">" in reason:
                    instance_parent = "".join((instance.split(">")[0], ">"))
                    reason = re.sub("<[^>]*>", instance_parent + " ", reason)
                    response["detail"]["reason"] = reason
                response["detail"]["instance"] = instance

            LOG.info("Submitted file is not valid against schema.")
            return ujson.dumps(response)

        except URLError as error:
            reason = f"Faulty file was provided. {error.reason}."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    def _parse_error_reason(self, error: ParseError) -> str:
        """Generate better error reason."""
        reason = str(error).split(":", maxsplit=1)[0]
        position = (str(error).split(":")[1])[1:]
        return f"Faulty XML file was given, {reason} at {position}"

    @property
    def is_valid(self) -> bool:
        """Quick method for checking validation result."""
        resp = ujson.loads(self.resp_body)
        return resp["isValid"]


def extend_with_default(validator_class: Draft202012Validator) -> Draft202012Validator:
    """Include default values present in JSON Schema.

    This feature is included even though some default values might cause
    unwanted behaviour when submitting a schema.

    Source: https://python-jsonschema.readthedocs.io FAQ
    """
    validate_properties = validator_class.VALIDATORS["properties"]

    def set_defaults(
        validator: Draft202012Validator, properties: Dict, instance: Draft202012Validator, schema: str
    ) -> Validator:
        for prop, subschema in properties.items():
            if "default" in subschema:
                instance.setdefault(prop, subschema["default"])

        for error in validate_properties(
            validator,
            properties,
            instance,
            schema,
        ):
            # Difficult to unit test
            yield error  # pragma: no cover

    return validators.extend(
        validator_class,
        {"properties": set_defaults},
    )


DefaultValidatingDraft202012Validator = extend_with_default(Draft202012Validator)


class JSONValidator:
    """JSON Validator implementation."""

    def __init__(self, json_data: Dict, schema_type: str) -> None:
        """Set variables.

        :param json_data: JSON content to be validated
        :param schema_type: Schema type to be used for validation
        """
        self.json_data = json_data
        self.schema_type = schema_type

    @property
    def validate(self) -> None:
        """Check validation against JSON schema.

        :raises: HTTPBadRequest if validation fails.
        """
        try:
            schema = JSONSchemaLoader().get_schema(self.schema_type)
            LOG.info("Validated against JSON schema.")
            DefaultValidatingDraft202012Validator(schema).validate(self.json_data)
        except SchemaNotFoundException as error:
            reason = f"{error} ({self.schema_type})"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        except ValidationError as e:
            if len(e.path) > 0:
                reason = f"Provided input does not seem correct for field: '{e.path[0]}'"
                LOG.debug(f"Provided JSON input: '{e.instance}'")
                LOG.exception(reason)
                raise web.HTTPBadRequest(reason=reason)

            reason = f"Provided input does not seem correct because: '{e.message}'"
            LOG.debug(f"Provided JSON input: '{e.instance}'")
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
