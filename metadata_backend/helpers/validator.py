"""Utility class for validating XML files."""

import re
import json
from io import StringIO
from urllib.error import URLError

from aiohttp import web
from xmlschema import XMLSchema, XMLSchemaValidationError
from xmlschema.etree import ElementTree, ParseError

from ..helpers.logger import LOG


class XMLValidator:
    """Validator implementation."""

    def __init__(self, schema: XMLSchema, xml: str) -> None:
        """Set Variables and initiate validation.

        :param schema: Schema to be used
        :param content: Content of XML file to be validated
        """
        self.schema = schema
        self.xml_content = xml
        self.resp_body = self.get_validation()
        self.xmlIsValid = self.is_valid()

    def get_validation(self) -> str:
        """Check validation and organize.

        :returns: JSON formatted string that provides details of validation
        :raises: HTTPBadRequest if URLError was raised during validation
        """
        try:
            self.schema.validate(self.xml_content)
            LOG.info("Submitted file is totally valid.")
            return json.dumps({"isValid": True})

        except ParseError as error:
            reason = parse_error_reason(error)
            # Manually find instance element
            lines = StringIO(self.xml_content).readlines()
            line = lines[error.position[0] - 1]  # line of instance
            instance = re.sub(r'^.*?<', '<', line)  # strip whitespaces

            LOG.info("Submitted file does not not contain valid XML syntax.")
            return json.dumps({"isValid": False, "detail":
                              {"reason": reason, "instance": instance}})

        except XMLSchemaValidationError as error:
            # Parse reason and instance from the validation error message
            reason = error.reason
            instance = ElementTree.tostring(error.elem, encoding="unicode")
            # Replace element address in reason with instance element
            if '<' and '>' in reason:
                instance_parent = ''.join((instance.split('>')[0], '>'))
                reason = re.sub("<[^>]*>", instance_parent + ' ', reason)

            LOG.info("Submitted file is not valid against schema.")
            return json.dumps({"isValid": False, "detail":
                              {"reason": reason, "instance": instance}})

        except URLError as error:
            reason = f"Faulty file was provided. {error.reason}."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    def parse_error_reason(self, error: ParseError) -> str:
        """Generate better error reason.

        :param error: The ParseError exception that was raised
        :returns: String with better error reason
        """
        reason = str(error).split(':')[0]
        position = (str(error).split(':')[1])[1:]
        return f"Faulty XML file was given, {reason} at {position}"

    def is_valid(self) -> bool:
        """Quick method for checking validation result.

        :returns: the value of isValid key in the validation detail JSON object
        """
        resp = json.loads(self.resp_body)
        return resp['isValid']
