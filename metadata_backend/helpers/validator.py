"""Utility classes for validating XML or JSON files."""

import re
from io import StringIO
from typing import Any

import ujson
from aiohttp import web
from defusedxml.ElementTree import ParseError, parse
from jsonschema import Draft202012Validator, validators
from jsonschema.exceptions import ValidationError
from jsonschema.protocols import Validator
from xmlschema import XMLSchema, XMLSchemaChildrenValidationError

from .logger import LOG
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
            root = parse(StringIO(self.xml_content)).getroot()
            errors: list[Any] = list(self.schema.iter_errors(root))
            if errors:
                LOG.info("Submitted file contains some errors.")
                response = self._format_xml_validation_error_reason(errors)
            else:
                LOG.info("Submitted file is totally valid.")
                response = {"status": 200}
            return ujson.dumps(response)

        except ParseError as error:
            reason, position = self._parse_error_response(error)
            # Manually find pointer element
            lines = StringIO(self.xml_content).readlines()
            line = lines[error.position[0] - 1]  # line of pointer
            pointer = line.lstrip().rstrip("\n")  # strip whitespaces and new line
            LOG.exception("Submitted file does not not contain valid XML syntax.")
            xml_error_response = self._format_xml_error_response()
            xml_error_response["errors"].append({"reason": reason, "position": position, "pointer": pointer})
            return ujson.dumps(xml_error_response)

    def _parse_error_response(self, error: ParseError) -> tuple[str, str]:
        """Generate better error detail and position for ParseError."""
        reason = str(error).split(":", maxsplit=1)[0]
        position = (str(error).split(":")[1])[1:]
        return reason, position

    def _format_xml_validation_error_reason(self, errors: list[Any]) -> dict[str, Any]:
        """Generate the response json object for validation error(s)."""
        xml_error_response = self._format_xml_error_response()
        found_lines = []
        for error in errors:
            reason = str(error.reason)
            path = str(error.path)
            # Find line number of error
            lines = self.xml_content.split("\n")
            elem_name = (
                error.obj[error.index].tag if isinstance(error, XMLSchemaChildrenValidationError) else error.elem.tag
            )
            for i, line in enumerate(lines, 1):
                if elem_name in line and i not in found_lines:
                    line_num = i
                    found_lines.append(i)
                    break
            if re.match(r"^.*at position [0-9]+", reason):
                # remove element position which doesn't provide useful information
                reason = re.sub(r" at position [0-9]+", "", reason)
            pointer = path if elem_name in path else f"{path}/{elem_name}"
            xml_error_response["errors"].append({"reason": reason, "position": f"line {line_num}", "pointer": pointer})
        return xml_error_response

    def _format_xml_error_response(self) -> dict[str, Any]:
        """Format error response according to JSON Problem specification:https://www.rfc-editor.org/rfc/rfc9457.html."""
        return {
            "title": "Bad Request",
            "status": 400,
            "detail": "Faulty XML file was given.",
            "errors": [],
        }

    @property
    def is_valid(self) -> bool:
        """Quick method for checking validation result."""
        resp = ujson.loads(self.resp_body)
        return bool(resp["status"] == 200)


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

        for error in validate_properties(  # pylint: disable=use-yield-from
            validator,
            properties,
            instance,
            schema,
        ):
            # Difficult to unit test
            # this is not an iterator so we cannot use yield from
            yield error  # pragma: no cover

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
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)
        except ValidationError as e:
            if len(e.path) > 0:
                reason = f"Provided input does not seem correct for field: '{e.path[0]}'"
                LOG.debug("Provided JSON input: '%r'", e.instance)
                LOG.exception(reason)
                raise web.HTTPBadRequest(reason=reason)

            reason = f"Provided input does not seem correct because: '{e.message}'"
            LOG.debug("Provided JSON input: '%r'", e.instance)
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)
