"""Tool to parse XML files to JSON."""

import re
from typing import Any, Dict, List, Union
from xml.etree.ElementTree import ParseError

from aiohttp import web
from xmlschema import XMLSchema, XMLSchemaConverter, XMLSchemaException
from xmlschema.compat import ordered_dict_class

from .schema_loader import SchemaLoader, SchemaNotFoundException


class MetadataXMLConverter(XMLSchemaConverter):
    """XML-JSON converter modified for EGA metadata, based on Abdera-converter.

    See following specs for more information about EGA schemas and Abdera:
    http://wiki.open311.org/JSON_and_XML_Conversion/#the-abdera-convention
    https://cwiki.apache.org/confluence/display/ABDERA/JSON+Serialization
    https://github.com/enasequence/schema/tree/master/src/main/resources/uk/ac/ebi/ena/sra/schema
    """

    def __init__(self,
                 namespaces: Any = None,
                 dict_class: Any = None,
                 list_class: Any = None,
                 **kwargs: Any) -> None:
        """Initialize converter and settings.

        :param namespaces: Map from namespace prefixes to URI.
        :param dict_class: Dictionary class to use for decoded data. Default is
        `dict`.
        :param list_class: List class to use for decoded data. Default is
        `list`.
        """
        kwargs.update(attr_prefix='', text_key='', cdata_prefix=None)
        super(MetadataXMLConverter, self).__init__(
            namespaces, dict_class, list_class, **kwargs
        )

    @property
    def lossy(self) -> bool:
        """Define that converter is lossy, xml structure can't be restored."""
        return True

    def element_decode(self,
                       data: Any,
                       xsd_element: Any,
                       xsd_type: Any = None,
                       level: int = 0) -> Union[Dict, List, str]:
        """Decode XML to JSON.

        Decoding strategy:
        - All keys are converted to CamelCase
        - Whitespace is parsed from strings
        - XML tags and their children are mostly converted to dict, except
          when there are multiple children with same name - then to list.
        - All "accession" keys are converted to "accesionId", key used by
          this program

        Corner cases:
        - If possible, self-closing xml tag is elevated as an attribute to its
          parent, otherwise "true" is added as its value.
        - If there is just one children and it is string, it is appended to
          same dictionary with its parents attributes with "value" as its key.
        """
        def _to_camel(name: str) -> str:
            """Convert underscore char notation to CamelCase."""
            _under_regex = re.compile(r'_([a-z])')
            return _under_regex.sub(lambda x: x.group(1).upper(), name)

        xsd_type = xsd_type or xsd_element.type
        if xsd_type.is_simple() or xsd_type.has_simple_content():
            children = (data.text if data.text is not None
                        and data.text != '' else None)
            if isinstance(children, str):
                children = " ".join(children.split())
        else:
            children = self.dict()
            for key, value, _ in self.map_content(data.content):
                key = _to_camel(key.lower())
                value = self.list() if value is None else value
                try:
                    children[key].append(value)
                except KeyError:
                    if isinstance(value, (self.list, list)) and value:
                        children[key] = self.list([value])
                    elif (isinstance(value, (self.dict, dict))
                          and len(value) == 1 and {} in value.values()):
                        children[key] = list(value.keys())[0]
                    else:
                        value is value if value != {} else "true"
                        children[key] = value
                except AttributeError:
                    children[key] = self.list([children[key], value])
        if data.attributes:
            tmp_dict = self.dict((_to_camel(key.lower()), value) for key, value
                                 in self.map_attributes(data.attributes))
            if "accession" in tmp_dict:
                tmp_dict["accessionId"] = tmp_dict.pop("accession")
            if children is not None:
                if isinstance(children, dict):
                    for key, value in children.items():
                        tmp_dict[key] = value
                else:
                    tmp_dict["value"] = children
            return self.dict(tmp_dict)
        else:
            return children


class XMLToJSONParser:
    """Methods to parse necessary data from different xml types."""

    def parse(self, schema_type: str, content: str) -> Dict:
        """Validate xml file and parse it to json.
        :param schema_type: Schema type to be used
        :param content: XML content to be parsed
        :returns: XML parsed to JSON
        """
        schema = self._load_schema(schema_type)
        self._validate(content, schema)
        return schema.to_dict(content,
                              converter=MetadataXMLConverter,
                              decimal_type=float,
                              dict_class=dict)[schema_type]

    @staticmethod
    def _load_schema(schema_type: str) -> XMLSchema:
        """Load schema for validation and xml-to-json decoding.

        :param schema_type: Schema type to be loaded
        :returns: Schema instance matching the given schema type
        :raises: HTTPBadRequest if schema wasn't found
        """
        loader = SchemaLoader()
        try:
            schema = loader.get_schema(schema_type)
        except (SchemaNotFoundException, XMLSchemaException) as error:
            reason = f"{error} {schema_type}"
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
        except (ParseError, XMLSchemaException):
            reason = ("Current request could not be processed"
                      " as the submitted file was not valid")
            raise web.HTTPBadRequest(reason=reason)
