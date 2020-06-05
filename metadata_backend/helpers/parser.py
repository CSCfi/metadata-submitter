"""Tool to parse XML files to JSON."""

import re
from datetime import datetime
from typing import Dict
from xml.etree.ElementTree import ParseError

from aiohttp import web
from dateutil.relativedelta import relativedelta
from xmlschema import AbderaConverter, XMLSchema, XMLSchemaException

from .schema_loader import SchemaLoader, SchemaNotFoundException


class XMLToJSONParser:
    """Methods to parse necessary data from different xml types."""

    def parse(self, type: str, content: str) -> Dict:
        """Parse necessary data from XML to make it queryable later.

        :param type: Submission type (schema) to be used
        :param content: XML content to be parsed
        :returns: XML parsed to JSON
        """
        # Validate
        schema = self._load_schema(type)
        self._validate(content, schema)

        # Parse json from XML
        content_json_raw = schema.to_dict(content, converter=AbderaConverter,
                                          decimal_type=float,
                                          dict_class=dict)[type.upper()]

        # Elevate content from ['children'][0] to top level
        to_be_elevated = content_json_raw['children'][0]
        del content_json_raw['children']
        content_json_elevated = {**content_json_raw, **to_be_elevated}

        # Format content to json-style formatting
        content_json = self._to_lowercase(content_json_elevated)

        if type == "study":
            content_json = self._modify_publish_dates(content_json)
        return content_json

    @staticmethod
    def _load_schema(xml_type: str) -> XMLSchema:
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
    def _modify_publish_dates(data: Dict) -> Dict:
        """Add study publicity status information to study object.

        By default this is two months from submission date (based on ENA
        submission model). Dates are written to database in UTC (see pymongo
        docs: https://api.mongodb.com/python/current/examples/datetimes.html)

        :param data: Study data as JSON
        :returns: Data extended with public date
        """
        data["publishDate"] = datetime.utcnow() + relativedelta(months=2)
        return data

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
