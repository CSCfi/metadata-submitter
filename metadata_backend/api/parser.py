"""Tool to parse XML files to JSON."""

import secrets
import string
from typing import Dict, List, Union

from aiohttp import web
from xmlschema import XMLSchema, XMLSchemaException

from ..helpers.schema_load import SchemaLoader, SchemaNotFoundException


class SubmissionXMLToJSONParser:
    """Methods to parse necessary data from different xml types.

    Currently only submission-type is parsed excplicitly, others are parsed
    just by flattening them.
    """

    def __init__(self) -> None:
        """Create SchemaLoader instance for loading schemas."""
        self.loader = SchemaLoader()

    def load_schema(self, xml_type: str) -> XMLSchema:
        """Load schema for validation and xml-to-json decoding.

        :param xml_type: Schema to be loaded
        :returns: Schema instance matching the given schema
        :raises: HTTPBadRequest if schema wasn't found
        """
        try:
            schema = self.loader.get_schema(xml_type)
        except (SchemaNotFoundException, XMLSchemaException) as error:
            reason = f"{error} {xml_type}"
            raise web.HTTPBadRequest(reason=reason)
        return schema

    @staticmethod
    def sort_actions_by_schemas(data: List) -> List:
        """Sort schemas according to their priority.

        Schemas need to be processed in certain order (for example 'study'
        submission needs to processed first in order to generate accession
        number for other submissions.

        Sorting order is based on ENA Metadata Model:
        https://ena-docs.readthedocs.io/en/latest/submit/general-guide/metadata.html

        This should probably be refactored later, since submissions can be also
        made via front-end or with actions in POST-request (i.e. without
        submission.xml).

        :param data: Data to be sorted
        :returns: Sorted list
        """
        order = {"study": 1, "sample": 2, "experiment": 3, "run": 4,
                 "analysis": 5, "dac": 6, "policy": 7, "dataset": 8,
                 "project": 9}
        return sorted(data, key=lambda x: order[x["schema"]])

    @staticmethod
    def flatten_and_parse_json(data: Dict) -> Dict:
        """Recursively flatten json and parse away unwanted characters.

        :param data: JSON to be flattened
        :returns: Flattened JSON
        """
        out = {}

        def flatten(content: Union[Dict, List], name: str = ""):
            if type(content) is dict:
                for key in content:
                    flatten(content[key], name + key + "_")
            elif type(content) is list:
                i = 0
                for element in content:
                    flatten(element, name + str(i) + "_")
                    i += 1
            else:
                if name[0] == "@":
                    name = name[1:]
                out[name[:-1]] = content

        flatten(data)
        return out

    @staticmethod
    def validate(content: str, schema: XMLSchema) -> None:
        """Validate XML with XMLSchema instance.

        :param content: XML to be validated
        :param schema: XMLSchema instance that validates XML.

        :raises: HTTPBadRequest if error was raised during validation
        """
        try:
            schema.validate(content)
        except (ValueError, XMLSchemaException) as error:
            reason = f"Validation error happened. Details: {error}"
            raise web.HTTPBadRequest(reason=reason)

    @staticmethod
    def generate_accession() -> str:
        """Generate accession number.

        returns: generated accession number
        """
        sequence = ''.join(secrets.choice(string.digits) for i in range(16))
        return f"EDAG{sequence}"

    def parse_study(self, data: Dict) -> Dict:
        """Parse data from study-type XML.

        Currently just flattens JSON and generates random accession number as
        placeholder (numbers are later on fetched from an another source).

        :param data: XML content as JSON
        :returns: Parsed data as JSON
        """
        flattened_data = self.flatten_and_parse_json(data)
        if "accession" not in flattened_data:
            flattened_data["accession"] = self.generate_accession()
        return flattened_data

    def parse_sample(self, data: Dict) -> Dict:
        """Parse data from sample-type XML.

        Currently just flattens JSON.

        :param data: XML content as JSON
        :returns: Parsed data as JSON
        """
        return self.flatten_and_parse_json(data)

    def parse_experiment(self, data: Dict) -> Dict:
        """Parse data from experiment-type XML.

        Currently just flattens JSON.

        :returns: Parsed data as JSON
        """
        return self.flatten_and_parse_json(data)

    def parse_run(self, data: Dict) -> Dict:
        """Parse data from run-type XML.

        Currently just flattens JSON.

        :param data: XML content as JSON
        :returns: Parsed data as JSON
        """
        return self.flatten_and_parse_json(data)

    def parse_analysis(self, data: Dict) -> Dict:
        """Parse data from sample-type XML.

        Currently just flattens JSON.

        :param data: XML content as JSON
        :returns: Parsed data as JSON
        """
        return self.flatten_and_parse_json(data)

    def parse_dac(self, data: Dict) -> Dict:
        """Parse data from dac-type XML.

        Currently just flattens JSON.

        :param data: XML content as JSON
        :returns: Parsed data as JSON
        """
        return self.flatten_and_parse_json(data)

    def parse_policy(self, data: Dict) -> Dict:
        """Parse data from sample-type XML.

        Currently just flattens JSON.

        :param data: XML content as JSON
        :returns: Parsed data as JSON
        """
        return self.flatten_and_parse_json(data)

    def parse_dataset(self, data: Dict) -> Dict:
        """Parse data from dataset-type XML.

        Currently just flattens JSON.

        :param data: XML content as JSON
        :returns: Parsed data as JSON
        """
        return self.flatten_and_parse_json(data)

    def parse_project(self, data: Dict) -> Dict:
        """Parse data from project-type XML.

        Currently just flattens JSON.

        :param data: XML content as JSON
        :returns: Parsed data as JSON
        """
        return self.flatten_and_parse_json(data)

    def parse_submission(self, data: Dict) -> Dict:
        """Parse data from submission-type XML.

        Especially for every submitted XML, we create a dict with info about
        schema, action and other attributes. This allows XMLs to be sorted
        according to their

        :param data: XML content as JSON
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
                sorted_infos = self.sort_actions_by_schemas(action_infos)
                parsed["action_infos"] = sorted_infos
        return parsed

    def parse(self, xml_type: str, content: str) -> Dict:
        """Parse necessary data from XML to make it queryable later.

        Since all XML types need to be parsed a bit differently, this method
        calls for correct parser based on given type.

        :param xml_type: Submission type (schema) to be used
        :param content: XML content to be parsed
        :returns: XML parsed to JSON
        """
        schema = self.load_schema(xml_type)
        self.validate(content, schema)
        content_json_raw = schema.to_dict(content)[xml_type.upper()][0]
        return getattr(self, f"parse_{xml_type}")(content_json_raw)
