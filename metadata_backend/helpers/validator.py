"""Utility classes for validating XML or JSON files."""

import re
from io import StringIO
from typing import Dict, List

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
            errors: List = list(self.schema.iter_errors(root))
            if errors:
                LOG.info("Submitted file contains some errors.")
                response = self._format_xml_validation_error_reason(errors)
            else:
                LOG.info("Submitted file is totally valid.")
                response = {"isValid": True}
            return ujson.dumps(response)

        except ParseError as error:
            reason = self._parse_error_reason(error)
            # Manually find instance element
            lines = StringIO(self.xml_content).readlines()
            line = lines[error.position[0] - 1]  # line of instance
            instance = re.sub(r"^.*?<", "<", line)  # strip whitespaces

            LOG.exception("Submitted file does not not contain valid XML syntax.")
            return ujson.dumps({"isValid": False, "detail": {"reason": reason, "instance": instance}})

    def _parse_error_reason(self, error: ParseError) -> str:
        """Generate better error reason for ParseError."""
        reason = str(error).split(":", maxsplit=1)[0]
        position = (str(error).split(":")[1])[1:]
        return f"Faulty XML file was given, {reason} at {position}"

    def _format_xml_validation_error_reason(self, errors: List) -> Dict:
        """Generate the response json object for validation error(s)."""
        response: Dict = {"isValid": False, "detail": {"reason": "", "instance": ""}}
        found_lines = []
        for error in errors:
            reason = str(error.reason)
            instance = str(error.path)

            # Add line number to error reason
            lines = self.xml_content.split("\n")
            elem_name = (
                error.obj[error.index].tag if isinstance(error, XMLSchemaChildrenValidationError) else error.elem.tag
            )
            for (i, line) in enumerate(lines, 1):
                if elem_name in line and i not in found_lines:
                    line_num = i
                    found_lines.append(i)
                    break
            if re.match(r"^.*at position [0-9]+", reason):
                # line number replaces element position which is more valuable information
                reason = re.sub(r"position [0-9]+", f"line {line_num}", reason)
            else:
                # line number still added as extra info to error reason
                reason = reason + f" (line {line_num})"
            response["detail"]["reason"] = response["detail"]["reason"] + reason + "\n"
            response["detail"]["instance"] = response["detail"]["instance"] + instance + "\n"

        response["detail"] = response["detail"][0] if len(response["detail"]) == 1 else response["detail"]
        return response

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
