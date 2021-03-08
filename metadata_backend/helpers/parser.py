"""Tool to parse XML files to JSON."""

import re
from typing import Any, Dict, List, Union

from aiohttp import web
from xmlschema import XMLSchema, XMLSchemaConverter, XMLSchemaException, XsdElement, XsdType

from .logger import LOG
from .schema_loader import SchemaNotFoundException, XMLSchemaLoader
from .validator import JSONValidator, XMLValidator
from pymongo import UpdateOne


class MetadataXMLConverter(XMLSchemaConverter):
    """XML-JSON converter modified for EGA metadata, based on Abdera-converter.

    See following specs for more information about EGA schemas and Abdera:
    http://wiki.open311.org/JSON_and_XML_Conversion/#the-abdera-convention
    https://cwiki.apache.org/confluence/display/ABDERA/JSON+Serialization
    https://github.com/enasequence/schema/tree/master/src/main/resources/uk/ac/ebi/ena/sra/schema
    """

    def __init__(self, namespaces: Any = None, dict_class: dict = None, list_class: list = None, **kwargs: Any) -> None:
        """Initialize converter and settings.

        :param namespaces: Map from namespace prefixes to URI.
        :param dict_class: Dictionary class to use for decoded data. Default is
        `dict`.
        :param list_class: List class to use for decoded data. Default is
        `list`.
        """
        kwargs.update(attr_prefix="", text_key="", cdata_prefix=None)
        super(MetadataXMLConverter, self).__init__(namespaces, dict_class, list_class, **kwargs)

    def _to_camel(self, name: str) -> str:
        """Convert underscore char notation to CamelCase."""
        _under_regex = re.compile(r"_([a-z])")
        return _under_regex.sub(lambda x: x.group(1).upper(), name)

    def _flatten(self, data: Any) -> Union[Dict, List, str, None]:
        links = [
            "studyLinks",
            "sampleLinks",
            "runLinks",
            "experimentLinks",
            "analysisLinks",
            "projectLinks",
            "policyLinks",
            "dacLinks",
            "datasetLinks",
            "assemblyLinks",
            "submissionLinks",
        ]

        attrs = [
            "studyAttributes",
            "sampleAttributes",
            "runAttributes",
            "experimentAttributes",
            "analysisAttributes",
            "projectAttributes",
            "policyAttributes",
            "dacAttributes",
            "datasetAttributes",
            "assemblyAttributes",
            "submissionAttributes",
        ]

        children = self.dict()
        for key, value, _ in self.map_content(data.content):
            key = self._to_camel(key.lower())

            if key in attrs and len(value) == 1:
                attrs = list(value.values())
                children[key] = attrs[0] if isinstance(attrs[0], list) else attrs
                continue

            if "studyType" in key:
                children[key] = value["existingStudyType"]
                continue

            if "platform" in key:
                children[key] = list(value.values())[0]["instrumentModel"]
                continue

            if "files" in key:
                children["files"] = list(value.values())
                continue

            if "dataBlock" in key:
                children["files"] = value["files"]
                continue

            if "spotDescriptor" in key:
                children[key] = value["spotDecodeSpec"]
                continue

            if key in links and len(value) == 1:
                grp = list()
                if isinstance(value[key[:-1]], dict):
                    grp = [it for it in value[key[:-1]].values()]
                    children[key] = grp
                else:
                    for item in value[key[:-1]]:
                        for k, v in item.items():
                            grp.append(v)

                children[key] = grp
                continue

            value = self.list() if value is None else value
            try:
                children[key].append(value)
            except KeyError:
                if isinstance(value, (self.list, list)) and value:
                    children[key] = self.list([value])
                elif isinstance(value, (self.dict, dict)) and len(value) == 1 and {} in value.values():
                    children[key] = list(value.keys())[0]
                else:
                    children[key] = value
            except AttributeError:
                children[key] = self.list([children[key], value])

        return children

    @property
    def lossy(self) -> bool:
        """Define that converter is lossy, xml structure can't be restored."""
        return True

    def element_decode(
        self,
        data: Any,
        xsd_element: XsdElement,
        xsd_type: XsdType = None,
        level: int = 0,
    ) -> Union[Dict, List, str, None]:
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
        - If there is dictionary of object type attributes (e.g.
          studyAttributes, experimentAttributes etc.), dictionary is replaced
          with its children, which is a list of those attributes.
        - If there is a dictionary type links (e.g studyLinks, sampleLinks
          etc. ) we group the types of links under an array, thus flattening
          the structure.
        - Study type takes the value of its attribute existingStudyType.
        - Platform data we assign the string value of the instrument Model.
        - dataBlock has the content of files array to be the same in run
          and analysis.
        - files is flatten for analysis and run so that it contains
          an array of files indiferent of the number.
        - spotDescriptor takes the value of its child spotDecodeSpec
        """
        xsd_type = xsd_type or xsd_element.type
        if xsd_type.simple_type is not None:
            children = data.text if data.text is not None and data.text != "" else None
            if isinstance(children, str):
                children = " ".join(children.split())
        else:
            children = self._flatten(data)

        if data.attributes:
            tmp = self.dict((self._to_camel(key.lower()), value) for key, value in self.map_attributes(data.attributes))
            if "accession" in tmp:
                tmp["accessionId"] = tmp.pop("accession")
            if children is not None:
                if isinstance(children, dict):
                    for key, value in children.items():
                        value = value if value != {} else "true"
                        tmp[key] = value
                else:
                    tmp["value"] = children
            return self.dict(tmp)
        else:
            return children


class XMLToJSONParser:
    """Methods to parse necessary data from different xml types."""

    def parse(self, schema_type: str, content: str) -> Dict:
        """Validate xml file and parse it to json.

        We validate resulting JSON against a JSON schema
        to be sure the resulting content is consistent.

        :param schema_type: Schema type to be used
        :param content: XML content to be parsed
        :returns: XML parsed to JSON
        :raises: HTTPBadRequest if error was raised during validation
        """
        schema = self._load_schema(schema_type)
        LOG.info(f"{schema_type} schema loaded.")
        validator = XMLValidator(schema, content)
        if not validator.is_valid:
            reason = "Current request could not be processed as the submitted file was not valid"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        result = schema.to_dict(content, converter=MetadataXMLConverter, decimal_type=float, dict_class=dict)[
            schema_type.lower()
        ]
        if schema_type.lower() != "submission":
            JSONValidator(result, schema_type.lower()).validate
        return result

    @staticmethod
    def _load_schema(schema_type: str) -> XMLSchema:
        """Load schema for validation and xml-to-json decoding.

        :param schema_type: Schema type to be loaded
        :returns: Schema instance matching the given schema type
        :raises: HTTPBadRequest if schema wasn't found
        """
        loader = XMLSchemaLoader()
        try:
            schema = loader.get_schema(schema_type)
        except (SchemaNotFoundException, XMLSchemaException) as error:
            reason = f"{error} {schema_type}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return schema


def jsonpatch_mongo(identifier: Dict, json_patch: List[Dict[str, Any]]) -> List:
    """Convert JSONpatch object to mongo query.

    :param jsonpatch: array with JSON patch actions
    :returns: dictionary of mongodb actions
    """
    queries: List[Any] = []
    for op in json_patch:
        if op["op"] == "add":
            if op["path"].endswith("/-"):
                queries.append(
                    UpdateOne(
                        identifier,
                        {
                            "$addToSet": {
                                op["path"][1:-2]: {
                                    "$each": op["value"] if isinstance(op["value"], list) else [op["value"]]
                                },
                            },
                        },
                    )
                )
            else:
                queries.append(UpdateOne(identifier, {"$set": {op["path"][1:].replace("/", "."): op["value"]}}))
        elif op["op"] == "replace":
            path = op["path"][1:-2] if op["path"].endswith("/-") else op["path"][1:].replace("/", ".")
            queries.append(UpdateOne(identifier, {"$set": {path: op["value"]}}))

    return queries
