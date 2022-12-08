"""Tool to parse XML and CSV files to JSON."""

import csv
import re
from io import StringIO
from typing import Any, Dict, List, Optional, Type, Union

from aiohttp import web
from pymongo import UpdateOne
from xmlschema import (
    ElementData,
    XMLSchema,
    XMLSchemaConverter,
    XMLSchemaException,
    XsdElement,
    XsdType,
    aliases,
)

from .logger import LOG
from .schema_loader import SchemaNotFoundException, XMLSchemaLoader
from .validator import JSONValidator, XMLValidator


class MetadataXMLConverter(XMLSchemaConverter):
    """XML-JSON converter modified for EGA metadata, based on Abdera-converter.

    See following specs for more information about EGA schemas and Abdera:
    http://wiki.open311.org/JSON_and_XML_Conversion/#the-abdera-convention
    https://cwiki.apache.org/confluence/display/ABDERA/JSON+Serialization
    https://github.com/enasequence/schema/tree/master/src/main/resources/uk/ac/ebi/ena/sra/schema
    """

    def __init__(
        self,
        namespaces: Optional[aliases.NamespacesType] = None,
        dict_class: Optional[Type[Dict[str, Any]]] = None,
        list_class: Optional[Type[List[Any]]] = None,
        # difficult to pinpoint type as xmlschema library does the same
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        """Initialize converter and settings.

        :param namespaces: Map from namespace prefixes to URI.
        :param dict_class: Dictionary class to use for decoded data. Default is
        `dict`.
        :param list_class: List class to use for decoded data. Default is
        `list`.
        """
        kwargs.update(attr_prefix="", text_key="", cdata_prefix=None)
        super().__init__(namespaces, dict_class, list_class, **kwargs)

    def _to_camel(self, name: str) -> str:
        """Convert underscore char notation to CamelCase."""
        _under_regex = re.compile(r"_([a-z])")
        return _under_regex.sub(lambda x: x.group(1).upper(), name)

    def _flatten(self, data: ElementData) -> Union[Dict, List, str, None]:
        """Address corner cases.

        :param schema_type: XML data
        :returns: XML element flattened.
        """
        links = {
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
        }

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
            "contacts",
            "dataUses",
            "attributeSet",
        ]

        refs = {"analysisRef", "sampleRef", "runRef", "experimentRef"}

        children: Any = self.dict()

        for key, value, _ in self.map_content(data.content):
            key = self._to_camel(key.lower())

            if key in set(attrs) and len(value) == 1:
                attrs = list(value.values())
                children[key] = attrs[0] if isinstance(attrs[0], list) else attrs
                continue

            if key == "attributes" and "attributeSet" not in value:
                attribs = list(value.values())
                attr_list = []
                for i in attribs:
                    if isinstance(i, list):
                        attr_list += i
                    else:
                        attr_list.append(i)
                children[key] = attr_list
                continue

            if "studyType" in key:
                children[key] = value["existingStudyType"]
                continue

            if "platform" in key:
                if isinstance(value, dict):
                    children[key] = list(value.values())[0]["instrumentModel"]
                else:
                    children[key] = value
                continue

            if key in {"processedReads", "referenceAlignment", "sequenceAnnotation", "assemblyAnnotation"}:
                if next(iter(value)) in {"assembly"}:
                    if next(iter(value["assembly"])) in {"standard", "custom"}:
                        value["assembly"] = next(iter(value["assembly"].values()))
                        if "accessionId" in value["assembly"]:
                            value["assembly"]["accession"] = value["assembly"].pop("accessionId")
                children[key] = value
                continue

            if key == "assemblyGraph" and "assembly" in value:
                attribs = value["assembly"]
                attr_list = []
                if isinstance(attribs, list):
                    for d in attribs:
                        for k, v in d.items():
                            v["accession"] = v.pop("accessionId")
                            attr_list.append(v)
                else:
                    v = next(iter(attribs.values()))
                    v["accession"] = v.pop("accessionId")
                    attr_list.append(v)

                children[key] = attr_list
                continue

            if key == "sequence":
                if "sequence" not in children:
                    children[key] = []
                children[key].append(value)
                for d in children[key]:
                    if "accessionId" in d:
                        d["accession"] = d.pop("accessionId")
                continue

            if "analysisType" in key:
                children[key] = value
                continue

            if "datasetType" in key:
                if "datasetType" not in children:
                    children[key] = []
                children[key].append(value)
                continue

            if "files" in key:
                if isinstance(value["file"], dict):
                    children["files"] = list(value.values())
                elif isinstance(value["file"], list):
                    children["files"] = value["file"]
                continue

            if "imageOf" in key:
                if "imageOf" not in children:
                    children[key] = []
                children[key].append(value)
                continue

            if "dataBlock" in key:
                children["files"] = value["files"]
                continue

            if "processing" in key:
                if not bool(value):
                    continue

            if "pipeSection" in key:
                if "pipeSection" not in children:
                    children[key] = []
                children[key].append(value)
                continue

            if "prevStepIndex" in key:
                if not bool(value):
                    children[key] = None
                    continue

            if "spotDescriptor" in key:
                children[key] = value["spotDecodeSpec"]
                continue

            if "libraryLayout" in key:
                children[key] = next(iter(value))
                children.update(next(iter(value.values())))
                continue

            if "policyText" in key:
                children["policy"] = {key: value}
                continue

            if key in refs:
                ref = key
                if ref not in children:
                    children[key] = []
                children[key].append(value)
                continue

            if "policyFile" in key:
                reason = "Policy file not supported"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)

            if "processing" in key:
                if not bool(value):
                    continue

            if "pipeSection" in key:
                children[key] = [value]
                continue

            if "prevStepIndex" in key:
                if not bool(value):
                    children[key] = None
                    continue

            if key in links and len(value) == 1:
                grp = []
                if isinstance(value[key[:-1]], dict):
                    grp = list(value[key[:-1]].values())
                    ks = list(value[key[:-1]])[0][:-4]
                    if ks == "url":
                        children[key] = grp
                    else:
                        children[key] = [{ks + k.capitalize(): v for k, v in d.items()} for d in grp]
                else:
                    for item in value[key[:-1]]:
                        for k, v in item.items():
                            ks = k[:-4]
                            if ks == "url":
                                grp.append({str(key): val for key, val in v.items()})
                            else:
                                grp.append({ks + str(key).capitalize(): val for key, val in v.items()})

                    children[key] = grp
                continue

            value = "" if value is None else value
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
        """Define that converter is lossy, XML structure can't be restored."""
        return True

    def element_decode(
        self,
        data: ElementData,
        xsd_element: XsdElement,
        xsd_type: Optional[XsdType] = None,
        level: int = 0,  # this is required for XMLSchemaConverter
    ) -> Union[Dict, List, str, None]:
        """Decode XML to JSON.

        Decoding strategy:
        - All keys are converted to CamelCase
        - Whitespace is parsed from strings
        - XML tags and their children are mostly converted to dict, except
          when there are multiple children with same name - then to list.
        - All "accession" keys are converted to "accessionId", key used by
          this program
        - default value if tag is empty string
        Corner cases:
        - If possible, self-closing XML tag is elevated as an attribute to its
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
        - process platform different for experiment
        - simplify assembly key and take the value from custom and standard keys
        - library layout takes the value of its first key as most times it will
          be just one key
        - analysis type processes empty tags differently to avoid confusions in
          JSON validator by making the analysisType string
        - datasetType should be an array and treat it as such even if one element
          selected
        - analysisRef, sampleRef, runRef, experimentRef need to be an array
        - experimentRef in run is an array with maxitems 1
        - if processing is empty do not show it as it is not required
        - processing pipeSection should be intepreted as an array
        - processing pipeSection prevStepIndex can be None if not specified empty
        - if sampleData does not exist (as it can only be added via forms) we will
          add it with default gender unknown
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
            # we add the bool(children) condition as for referenceAlignment
            # this is to distinguish between the attributes
            if "accession" in tmp:
                tmp["accessionId"] = tmp.pop("accession")
            if "sampleName" in tmp and "sampleData" not in tmp:
                tmp["sampleData"] = {"gender": "unknown"}
            if children is not None:
                if isinstance(children, dict):
                    for key, value in children.items():
                        value = value if value != {} else "true"
                        tmp[key] = value
                else:
                    tmp["value"] = children
            return self.dict(tmp)

        return children


class XMLToJSONParser:
    """Methods to parse necessary data from different XML types."""

    def parse(self, schema_type: str, content: str) -> Dict:
        """Validate XML file and parse it to JSON.

        We validate resulting JSON against a JSON schema
        to be sure the resulting content is consistent.

        :param schema_type: Schema type to be used
        :param content: XML content to be parsed
        :returns: XML parsed to JSON
        :raises: HTTPBadRequest if error was raised during validation
        """
        schema = self._load_schema(schema_type)
        LOG.info("%r XML schema loaded.", schema_type)
        validator = XMLValidator(schema, content)
        if not validator.is_valid:
            reason = "Current request could not be processed as the submitted file was not valid"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        # result is of type:
        # Union[Any, List[Any], Tuple[None, List[XMLSchemaValidationError]],
        # Tuple[Any, List[XMLSchemaValidationError]], Tuple[List[Any], List[XMLSchemaValidationError]]]
        # however we expect any type as it is easier to work with
        result: Any = schema.to_dict(content, converter=MetadataXMLConverter, decimal_type=float, dict_class=dict)
        _schema_type: str = schema_type.lower()
        # BP sample files require special treatment
        if _schema_type == "bpsample":
            result = self._organize_bp_sample_objects(result)
        # Validate each JSON object separately if an array of objects is parsed
        results = result[_schema_type] if isinstance(result[_schema_type], list) else [result[_schema_type]]
        if _schema_type != "submission":
            for obj in results:
                JSONValidator(obj, _schema_type).validate
        return result[_schema_type]

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
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)
        return schema

    @staticmethod
    def _organize_bp_sample_objects(data: Dict) -> Dict:
        """Handle BP Sample data after it was parsed from an XML so it can be validated and added to db.

        :param data: BP sample objects in JSON format
        :returns: Organized BP sample objects
        """

        # Helper function for separating sample objects
        def _separate_samples(item: Union[Dict, List[Dict]], title: str) -> List[Dict]:
            if isinstance(item, list) and len(item) > 0:
                return [{title: i} for i in item]
            return [{title: item}] if isinstance(item, dict) else []

        # Separate biological beings, cases, specimen, blocks and slides from the data that was extracted from the XML
        bio_beings = data["biologicalBeing"] if "biologicalBeing" in data else []
        bio_beings = _separate_samples(bio_beings, "biologicalBeing")
        cases = data["case"] if "case" in data else []
        cases = _separate_samples(cases, "case")
        specimens = data["specimen"] if "specimen" in data else []
        specimens = _separate_samples(specimens, "specimen")
        blocks = data["block"] if "block" in data else []
        blocks = _separate_samples(blocks, "block")
        slides = data["slide"] if "slide" in data else []
        slides = _separate_samples(slides, "slide")

        # Return all samples as an array under bpsample schema name
        samples: List[Dict] = bio_beings + cases + specimens + blocks + slides
        return {"bpsample": samples}


class CSVToJSONParser:
    """Methods to parse and convert data from CSV files to JSON format."""

    def parse(self, schema_type: str, content: str) -> List:
        """Parse a CSV file, convert it to JSON and validate against JSON schema.

        :param schema_type: Schema type of the file to be parsed
        :param content: CSV content to be parsed
        :returns: CSV parsed to JSON
        :raises: HTTPBadRequest if error was raised during parsing or validation
        """
        csv_reader = csv.DictReader(StringIO(content), delimiter=",", quoting=csv.QUOTE_NONE)

        _sample_list = {
            "title",
            "alias",
            "description",
            "subjectId",
            "bioSampleId",
            "caseOrControl",
            "gender",
            "organismPart",
            "cellLine",
            "region",
            "phenotype",
        }

        if (
            csv_reader.fieldnames
            and schema_type == "sample"
            and all(elem in _sample_list for elem in csv_reader.fieldnames)
        ):
            LOG.debug("sample CSV file has the correct header")
        else:
            reason = f"{schema_type} does not contain the correct header fields: {_sample_list}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        rows = list(csv_reader)

        if not rows:
            reason = "CSV file appears to be incomplete. No rows of data were parsed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        _parsed = []
        for row in rows:
            LOG.debug("current row: %d", row)
            _tmp: Dict[str, Any] = row
            # This is required to pass validation against current sample schema
            if schema_type == "sample" and "sampleName" not in row:
                # Without TaxonID provided we assume the sample relates to
                # Homo Sapien which has default TaxonID of 9606
                _tmp["sampleName"] = {"taxonId": 9606}
            # if geneder exists we will format it accordingly
            if not bool(_tmp["gender"]):
                _tmp["sampleData"] = {"gender": "unknown"}
            else:
                _tmp["sampleData"] = {"gender": _tmp["gender"]}
            _tmp.pop("gender")
            JSONValidator(_tmp, schema_type.lower()).validate
            _parsed.append(_tmp)

        LOG.info("CSV was successfully converted to %d JSON object(s).", len(_parsed))
        return _parsed


def jsonpatch_mongo(identifier: Dict, json_patch: List[Dict]) -> List:
    """Convert JSONpatch object to mongo query.

    :param identifier: object database ID
    :param json_patch: array with JSON patch actions
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
                                op["path"][1:-2].replace("/", "."): {
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
            if op.get("match", None):
                identifier.update(op["match"])
            queries.append(UpdateOne(identifier, {"$set": {path: op["value"]}}))

    return queries
