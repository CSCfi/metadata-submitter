"""Tool to parse XML files to JSON."""

import re
import secrets
import string
from datetime import datetime
from typing import Dict, List
from xml.etree.ElementTree import ParseError

from aiohttp import web
from dateutil.relativedelta import relativedelta
from xmlschema import AbderaConverter, XMLSchema, XMLSchemaException

from ..conf.conf import object_types
from .schema_loader import SchemaLoader, SchemaNotFoundException


class XMLToJSONParser:
    """Methods to parse necessary data from different xml types."""

    def parse(self, xml_type: str, content: str) -> Dict:
        """Parse necessary data from XML to make it queryable later.

        All submitted objects are first parsed on generic level, then formatted
        formatted and finally passed to schema-specific parser.

        :param xml_type: Submission type (schema) to be used
        :param content: XML content to be parsed
        :returns: XML parsed to JSON
        """
        # Validate
        schema = self._load_schema(xml_type)
        self._validate(content, schema)

        # Parse json from XML
        content_json_raw = schema.to_dict(content, converter=AbderaConverter,
                                          decimal_type=float,
                                          dict_class=dict)[xml_type.upper()]

        # Elevate content from ['children'][0] to top level
        to_be_elevated = content_json_raw['children'][0]
        del content_json_raw['children']
        content_json_elevated = {**content_json_raw, **to_be_elevated}

        # Format content to json-style formatting
        content_json_formatted = self._to_lowercase(content_json_elevated)

        # Add accessionId
        content_json_formatted["accessionId"] = self._generate_accession_id()

        # Run through schema-specific parser and return the result
        return getattr(self, f"_parse_{xml_type}")(content_json_formatted)

    def _load_schema(self, xml_type: str) -> XMLSchema:
        """Load schema for validation and xml-to-json decoding.

        :param xml_type: Schema to be loaded
        :returns: Schema instance matching the given schema
        :raises: HTTPBadRequest if schema wasn't found
        """
        loader = SchemaLoader()
        try:
            schema = loader.get_schema(xml_type)
        except (SchemaNotFoundException, XMLSchemaException) as error:
            reason = f"{error} {xml_type}"
            raise web.HTTPBadRequest(reason=reason)
        return schema

    @staticmethod
    def _validate(content: str, schema: XMLSchema) -> None:
        """Validate XML with XMLSchema instance.

        :param content: XML to be validated
        :param schema: XMLSchema instance that validates XML.

        :raises: HTTPBadRequest if error was raised during validation
        """
        try:
            schema.validate(content)
        except (ParseError, XMLSchemaException) as error:
            reason = f"Validation error happened. Details: {error}"
            raise web.HTTPBadRequest(reason=reason)

    @staticmethod
    def _generate_accession_id() -> str:
        """Generate accession number.

        :returns: generated accession number
        """
        sequence = ''.join(secrets.choice(string.digits) for i in range(16))
        return f"EDAG{sequence}"

    def _parse_study(self, data: Dict) -> Dict:
        """Parse data from study-type XML.

        Adds study publicity status information to study object. By default
        this is two months from submission date (based on ENA submission
        model). Dates are written to database in UTC (see pymongo docs:
        https://api.mongodb.com/python/current/examples/datetimes.html)

        Should be later modified to give user possibility to set publicity
        status in submission from front-end / via POST.

        :param data: XML content as JSON
        :returns: Parsed data as JSON
        """
        data["publishDate"] = datetime.now() + relativedelta(months=2)
        return data

    def _parse_sample(self, data: Dict) -> Dict:
        """Parse data from sample-type XML.

        Currently doesn't add anything extra.

        :param data: XML content as JSON
        :returns: Parsed data as JSON
        """
        return data

    def _parse_experiment(self, data: Dict) -> Dict:
        """Parse data from experiment-type XML.

        Currently doesn't add anything extra.

        :returns: Parsed data as JSON
        """
        return data

    def _parse_run(self, data: Dict) -> Dict:
        """Parse data from run-type XML.

        Currently doesn't add anything extra.

        :param data: XML content as JSON
        :returns: Parsed data as JSON
        """
        return data

    def _parse_analysis(self, data: Dict) -> Dict:
        """Parse data from sample-type XML.

        Currently doesn't add anything extra.

        :param data: XML content as JSON
        :returns: Parsed data as JSON
        """
        return data

    def _parse_dac(self, data: Dict) -> Dict:
        """Parse data from dac-type XML.

        Currently doesn't add anything extra.

        :param data: XML content as JSON
        :returns: Parsed data as JSON
        """
        return data

    def _parse_policy(self, data: Dict) -> Dict:
        """Parse data from sample-type XML.

        Currently doesn't add anything extra.

        :param data: XML content as JSON
        :returns: Parsed data as JSON
        """
        return data

    def _parse_dataset(self, data: Dict) -> Dict:
        """Parse data from dataset-type XML.

        Currently doesn't add anything extra.

        :param data: XML content as JSON
        :returns: Parsed data as JSON
        """
        return data

    def _parse_project(self, data: Dict) -> Dict:
        """Parse data from project-type XML.

        Currently doesn't add anything extra.

        :param data: XML content as JSON
        :returns: Parsed data as JSON
        """
        return data

    def _parse_submission(self, data: Dict) -> Dict:
        """Parse data from submission-type XML.

        Especially for every submitted XML, we create a dict with info about
        schema, action and other attributes. This allows XMLs to be sorted
        according to their

        :param data: XML content as JSON
        :raises HTTPError if there ins't enough data in submission.xml to
        process files later
        :returns: Parsed data as JSON
        """
        parsed = {}
        for key, value in data.items():
            if key[0] == "@":
                parsed[key[1:].lower()] = value.lower()
            if key == "ACTIONS":
                action_infos = []
                for action_set in value["ACTION"]:
                    for action, data in action_set.items():
                        if data:
                            action_info = {}
                            for attribute, content in data.items():
                                if attribute[0] == "@":
                                    attribute = attribute[1:]
                                action_info[attribute] = content
                            action_info["action"] = action.lower()
                            action_infos.append(action_info)
                        else:
                            reason = (f"You also need to provide necessary"
                                      f" information for submission action."
                                      f" Now {action} was provided without any"
                                      f" extra information.")
                            raise web.HTTPBadRequest(reason=reason)
                        action_infos.append(action_info)
                sorted_infos = self._sort_actions_by_schemas(action_infos)
                parsed["action_infos"] = sorted_infos
        return parsed

    @staticmethod
    def _sort_actions_by_schemas(data: List) -> List:
        """Sort schemas according to their priority.

        Schemas need to be processed in certain order (for example 'study'
        submission needs to processed first in order to generate accession
        number for other submissions.

        Sorting order is based on ENA Metadata Model:
        https://ena-docs.readthedocs.io/en/latest/submit/general-guide/metadata.html

        This should probably be refactored later, since submissions can be also
        made via front-end (i.e. without submission.xml).

        :param data: Data to be sorted
        :returns: Sorted list
        """
        return sorted(data, key=lambda x: object_types[x["schema"]])

    def _to_lowercase(self, obj: Dict) -> Dict:
        """Make dictionary lowercase and convert keys to CamelCase.

        Also clears away any empty elements that xml-json -conversion
        caused.
        """
        def _to_camel(name: str) -> str:
            """Convert underscore char notation to CamelCase."""
            _under_regex = re.compile(r'_([a-z])')
            return _under_regex.sub(lambda x: x.group(1).upper(), name)

        if isinstance(obj, dict):
            return {_to_camel(k.lower()): self._to_lowercase(v)
                    for k, v in obj.items() if v}
        elif isinstance(obj, (list, set, tuple)):
            t = type(obj)
            return t(self._to_lowercase(o) for o in obj if o)
        elif isinstance(obj, str):
            return _to_camel(obj)
        else:
            return obj
