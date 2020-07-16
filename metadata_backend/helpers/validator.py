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
        """Variables."""
        self.schema = schema
        self.xml_content = xml
        self.resp_body = self.get_validation()

    def get_validation(self) -> str:
        """Where validation happens."""
        try:
            self.schema.validate(self.xml_content)
            # LOG.info(f"Submitted file is valid against {schema_type} schema."
            return json.dumps({"isValid": True})

        except ParseError as error:
            reason = str(error).split(':')[0]
            position = (str(error).split(':')[1])[1:]
            full_reason = f"Faulty XML file was given, {reason} at {position}"
            # Manually find instance element
            lines = StringIO(self.xml_content).readlines()
            line = lines[error.position[0] - 1]  # line of instance
            instance = re.sub(r'^.*?<', '<', line)  # strip whitespaces

            LOG.info("Submitted file does not not contain valid XML syntax.")
            return json.dumps({"isValid": False, "detail":
                              {"reason": full_reason, "instance": instance}})

        except XMLSchemaValidationError as error:
            # Parse reason and instance from the validation error message
            reason = error.reason
            instance = ElementTree.tostring(error.elem, encoding="unicode")
            # Replace element address in reason with instance element
            if '<' and '>' in reason:
                instance_parent = ''.join((instance.split('>')[0], '>'))
                reason = re.sub("<[^>]*>", instance_parent + ' ', reason)

            # LOG.info(f"Submitted file is not valid against {schema_type} "
            #          "schema.")
            return json.dumps({"isValid": False, "detail":
                              {"reason": reason, "instance": instance}})

        except URLError as error:
            reason = f"Faulty file was provided. {error.reason}."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
