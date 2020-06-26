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
        `dict` for Python 3.6+ or `OrderedDict` for previous versions.
        :param list_class: List class to use for decoded data. Default is
        `list`.
        """
        kwargs.update(attr_prefix='', text_key='', cdata_prefix=None)
        super(MetadataXMLConverter, self).__init__(
            namespaces,
            dict_class or ordered_dict_class,
            list_class,
            **kwargs
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
        """Decode xml file to json.

        Does following things:
        - Attributes are presented as key-value pairs in dictionaries
        - Extra whitespace is parsed from strings
        - All keys are converted to CamelCase

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
            for name, value, xsd_child in self.map_content(data.content):
                name = _to_camel(name.lower())
                if value is None:
                    value = self.list()
                try:
                    children[name].append(value)
                except KeyError:
                    if isinstance(value, (self.list, list)) and value:
                        children[name] = self.list([value])
                    else:
                        children[name] = value
                except AttributeError:
                    children[name] = self.list([children[name], value])

        if data.attributes:
            if children != []:
                tmpdict = self.dict((_to_camel(k.lower()), v) for k, v in
                                    self.map_attributes(data.attributes))
                if children is not None:
                    if isinstance(children, str):
                        tmpdict["value"] = children.replace('\\n', '\n')
                    else:
                        for k, v in children.items():
                            tmpdict[k] = v
                return self.dict(tmpdict)
            else:
                return self.dict((_to_camel(k.lower()), v) for k, v in
                                 self.map_attributes(data.attributes))
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
