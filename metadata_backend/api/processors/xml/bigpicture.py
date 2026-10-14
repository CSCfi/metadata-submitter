import re
from collections.abc import AsyncIterator, Iterable
from enum import StrEnum
from io import BytesIO
from pathlib import Path

from lxml import etree
from lxml.etree import _Element as Element  # noqa

from ...exceptions import UserException
from ..exceptions import InvalidDocumentException
from .models import XmlIdentifierPath, XmlObjectConfig, XmlObjectPaths, XmlReferencePaths, xml_schema_path
from .processors import XmlDocumentProcessor, XmlObjectProcessor, XmlProcessor

BP_XML_SCHEMA_2_DIR = Path(__file__).parent.parent.parent.parent / "schemas" / "xml" / "bigpicture" / "2.0"
BP_XML_SCHEMA_3_DIR = Path(__file__).parent.parent.parent.parent / "schemas" / "xml" / "bigpicture" / "3.0"


class BigpictureVersion(StrEnum):
    """Supported Bigpicture metadata versions, named after schema directories."""

    V2_0 = "2.0"
    V3_0 = "3.0"


# The dataset XML schema restricts METADATA_STANDARD to "<major>.<minor>.<patch>".
_BP_METADATA_STANDARD_PATTERN = re.compile(r"(\d+\.\d+)\.\d+")


# The schema type must match the XML schema file name without the ".xsd" extension.

BP_ANNOTATION_SCHEMA = "annotation"
BP_ANNOTATION_TASK_SCHEMA = "annotation_task"  # Since 3.0.
BP_ANNOTATOR_SCHEMA = "annotator"  # Since 3.0.
BP_DATASET_SCHEMA = "dataset"
BP_IMAGE_SCHEMA = "image"
BP_LANDING_PAGE_SCHEMA = "landing_page"
BP_OBSERVATION_SCHEMA = "observation"
BP_OBSERVER_SCHEMA = "observer"
BP_ONTOLOGY_SCHEMA = "ontology"  # Since 3.0.
BP_ORGANISATION_SCHEMA = "organisation"
BP_POLICY_SCHEMA = "policy"
BP_REMS_SCHEMA = "rems"
BP_SAMPLE_SCHEMA = "sample"
BP_STAINING_SCHEMA = "staining"

BP_ANNOTATION_PATH = "/ANNOTATION"
BP_ANNOTATION_TASK_PATH = "/ANNOTATION_TASK"
BP_ANNOTATOR_PATH = "/ANNOTATOR"
BP_DATASET_PATH = "/DATASET"
BP_IMAGE_PATH = "/IMAGE"
BP_LANDING_PAGE_PATH = "/LANDING_PAGE"
BP_OBSERVATION_PATH = "/OBSERVATION"
BP_OBSERVER_PATH = "/OBSERVER"
BP_ONTOLOGY_PATH = "/ONTOLOGY"
BP_ORGANISATION_PATH = "/ORGANISATION"
BP_POLICY_PATH = "/POLICY"
BP_REMS_PATH = "/REMS"
BP_SAMPLE_BIOLOGICAL_BEING_PATH = "/BIOLOGICAL_BEING"
BP_SAMPLE_SLIDE_PATH = "/SLIDE"
BP_SAMPLE_SPECIMEN_PATH = "/SPECIMEN"
BP_SAMPLE_BLOCK_PATH = "/BLOCK"
BP_SAMPLE_CASE_PATH = "/CASE"
BP_STAINING_PATH = "/STAINING"

BP_ANNOTATION_SCHEMA_AND_PATH = (BP_ANNOTATION_SCHEMA, BP_ANNOTATION_PATH)
BP_ANNOTATION_TASK_SCHEMA_AND_PATH = (BP_ANNOTATION_TASK_SCHEMA, BP_ANNOTATION_TASK_PATH)
BP_ANNOTATOR_SCHEMA_AND_PATH = (BP_ANNOTATOR_SCHEMA, BP_ANNOTATOR_PATH)
BP_DATASET_SCHEMA_AND_PATH = (BP_DATASET_SCHEMA, BP_DATASET_PATH)
BP_IMAGE_SCHEMA_AND_PATH = (BP_IMAGE_SCHEMA, BP_IMAGE_PATH)
BP_LANDING_PAGE_SCHEMA_AND_PATH = (BP_LANDING_PAGE_SCHEMA, BP_LANDING_PAGE_PATH)
BP_OBSERVATION_SCHEMA_AND_PATH = (BP_OBSERVATION_SCHEMA, BP_OBSERVATION_PATH)
BP_OBSERVER_SCHEMA_AND_PATH = (BP_OBSERVER_SCHEMA, BP_OBSERVER_PATH)
BP_ONTOLOGY_SCHEMA_AND_PATH = (BP_ONTOLOGY_SCHEMA, BP_ONTOLOGY_PATH)
BP_ORGANISATION_SCHEMA_AND_PATH = (BP_ORGANISATION_SCHEMA, BP_ORGANISATION_PATH)
BP_POLICY_SCHEMA_AND_PATH = (BP_POLICY_SCHEMA, BP_POLICY_PATH)
BP_REMS_SCHEMA_AND_PATH = (BP_REMS_SCHEMA, BP_REMS_PATH)
BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH = (BP_SAMPLE_SCHEMA, BP_SAMPLE_BIOLOGICAL_BEING_PATH)
BP_SAMPLE_SLIDE_SCHEMA_AND_PATH = (BP_SAMPLE_SCHEMA, BP_SAMPLE_SLIDE_PATH)
BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH = (BP_SAMPLE_SCHEMA, BP_SAMPLE_SPECIMEN_PATH)
BP_SAMPLE_BLOCK_SCHEMA_AND_PATH = (BP_SAMPLE_SCHEMA, BP_SAMPLE_BLOCK_PATH)
BP_SAMPLE_CASE_SCHEMA_AND_PATH = (BP_SAMPLE_SCHEMA, BP_SAMPLE_CASE_PATH)
BP_STAINING_SCHEMA_AND_PATH = (BP_STAINING_SCHEMA, BP_STAINING_PATH)

BP_ANNOTATION_SET_PATH = "/ANNOTATION_SET"
BP_ANNOTATION_TASK_SET_PATH = "/ANNOTATION_TASK_SET"
BP_ANNOTATOR_SET_PATH = "/ANNOTATOR_SET"
BP_DATASET_SET_PATH = "/DATASET_SET"
BP_IMAGE_SET_PATH = "/IMAGE_SET"
BP_LANDING_PAGE_SET_PATH = "/LANDING_PAGE_SET"
BP_OBSERVATION_SET_PATH = "/OBSERVATION_SET"
BP_OBSERVER_SET_PATH = "/OBSERVER_SET"
BP_ONTOLOGY_SET_PATH = "/ONTOLOGY_SET"
BP_ORGANISATION_SET_PATH = "/ORGANISATION_SET"
BP_POLICY_SET_PATH = "/POLICY_SET"
BP_REMS_SET_PATH = "/REMS_SET"
BP_SAMPLE_SET_PATH = "/SAMPLE_SET"
BP_STAINING_SET_PATH = "/STAINING_SET"


def _get_xml_object_type_bp(root_path: str) -> str:
    return root_path.lstrip(".").lstrip("/").lower()


BP_ANNOTATION_OBJECT_TYPE = _get_xml_object_type_bp(BP_ANNOTATION_PATH)
BP_ANNOTATION_TASK_OBJECT_TYPE = _get_xml_object_type_bp(BP_ANNOTATION_TASK_PATH)
BP_ANNOTATOR_OBJECT_TYPE = _get_xml_object_type_bp(BP_ANNOTATOR_PATH)
BP_DATASET_OBJECT_TYPE = _get_xml_object_type_bp(BP_DATASET_PATH)
BP_IMAGE_OBJECT_TYPE = _get_xml_object_type_bp(BP_IMAGE_PATH)
BP_LANDING_PAGE_OBJECT_TYPE = _get_xml_object_type_bp(BP_LANDING_PAGE_PATH)
BP_OBSERVATION_OBJECT_TYPE = _get_xml_object_type_bp(BP_OBSERVATION_PATH)
BP_OBSERVER_OBJECT_TYPE = _get_xml_object_type_bp(BP_OBSERVER_PATH)
BP_ONTOLOGY_OBJECT_TYPE = _get_xml_object_type_bp(BP_ONTOLOGY_PATH)
BP_ORGANISATION_OBJECT_TYPE = _get_xml_object_type_bp(BP_ORGANISATION_PATH)
BP_POLICY_OBJECT_TYPE = _get_xml_object_type_bp(BP_POLICY_PATH)
BP_REMS_OBJECT_TYPE = _get_xml_object_type_bp(BP_REMS_PATH)
BP_SAMPLE_BIOLOGICAL_BEING_OBJECT_TYPE = _get_xml_object_type_bp(BP_SAMPLE_BIOLOGICAL_BEING_PATH)
BP_SAMPLE_SLIDE_OBJECT_TYPE = _get_xml_object_type_bp(BP_SAMPLE_SLIDE_PATH)
BP_SAMPLE_SPECIMEN_OBJECT_TYPE = _get_xml_object_type_bp(BP_SAMPLE_SPECIMEN_PATH)
BP_SAMPLE_BLOCK_OBJECT_TYPE = _get_xml_object_type_bp(BP_SAMPLE_BLOCK_PATH)
BP_SAMPLE_CASE_OBJECT_TYPE = _get_xml_object_type_bp(BP_SAMPLE_CASE_PATH)
BP_STAINING_OBJECT_TYPE = _get_xml_object_type_bp(BP_STAINING_PATH)
BP_SUBMISSION_OBJECT_TYPE = "submission"  # Implicit object type.
BP_FILE_OBJECT_TYPE = "file"  # Implicit object type.

# Object types of all supported versions.
BP_OBJECT_TYPES = [
    BP_ANNOTATION_OBJECT_TYPE,
    BP_ANNOTATION_TASK_OBJECT_TYPE,
    BP_ANNOTATOR_OBJECT_TYPE,
    BP_DATASET_OBJECT_TYPE,
    BP_IMAGE_OBJECT_TYPE,
    BP_LANDING_PAGE_OBJECT_TYPE,
    BP_OBSERVATION_OBJECT_TYPE,
    BP_OBSERVER_OBJECT_TYPE,
    BP_ONTOLOGY_OBJECT_TYPE,
    BP_ORGANISATION_OBJECT_TYPE,
    BP_POLICY_OBJECT_TYPE,
    BP_REMS_OBJECT_TYPE,
    BP_SAMPLE_BIOLOGICAL_BEING_OBJECT_TYPE,
    BP_SAMPLE_SLIDE_OBJECT_TYPE,
    BP_SAMPLE_SPECIMEN_OBJECT_TYPE,
    BP_SAMPLE_BLOCK_OBJECT_TYPE,
    BP_SAMPLE_CASE_OBJECT_TYPE,
    BP_STAINING_OBJECT_TYPE,
    BP_SUBMISSION_OBJECT_TYPE,
    BP_FILE_OBJECT_TYPE,
]

BP_SAMPLE_OBJECT_TYPES = [
    BP_SAMPLE_BIOLOGICAL_BEING_OBJECT_TYPE,
    BP_SAMPLE_SLIDE_OBJECT_TYPE,
    BP_SAMPLE_SPECIMEN_OBJECT_TYPE,
    BP_SAMPLE_BLOCK_OBJECT_TYPE,
    BP_SAMPLE_CASE_OBJECT_TYPE,
]

BP_MANDATORY_OBJECT_TYPES = [
    BP_DATASET_OBJECT_TYPE,
    BP_IMAGE_OBJECT_TYPE,
    BP_LANDING_PAGE_OBJECT_TYPE,
    BP_OBSERVATION_OBJECT_TYPE,
    BP_ORGANISATION_OBJECT_TYPE,
    BP_POLICY_OBJECT_TYPE,
    BP_REMS_OBJECT_TYPE,
    BP_SAMPLE_BIOLOGICAL_BEING_OBJECT_TYPE,
    BP_SAMPLE_BLOCK_OBJECT_TYPE,
    BP_SAMPLE_SLIDE_OBJECT_TYPE,
    BP_SAMPLE_SPECIMEN_OBJECT_TYPE,
    BP_STAINING_OBJECT_TYPE,
]

BP_SINGLE_OBJECT_TYPES = [
    BP_DATASET_OBJECT_TYPE,
    BP_LANDING_PAGE_OBJECT_TYPE,
    BP_ORGANISATION_OBJECT_TYPE,
    BP_POLICY_OBJECT_TYPE,
    BP_REMS_OBJECT_TYPE,
]


def get_xml_object_type_schema(object_type: str) -> str:
    if object_type in BP_SAMPLE_OBJECT_TYPES:
        return BP_SAMPLE_SCHEMA
    if object_type == BP_ANNOTATION_OBJECT_TYPE:
        return BP_ANNOTATION_SCHEMA
    if object_type == BP_ANNOTATION_TASK_OBJECT_TYPE:
        return BP_ANNOTATION_TASK_SCHEMA
    if object_type == BP_ANNOTATOR_OBJECT_TYPE:
        return BP_ANNOTATOR_SCHEMA
    if object_type == BP_DATASET_OBJECT_TYPE:
        return BP_DATASET_SCHEMA
    if object_type == BP_IMAGE_OBJECT_TYPE:
        return BP_IMAGE_SCHEMA
    if object_type == BP_LANDING_PAGE_OBJECT_TYPE:
        return BP_LANDING_PAGE_SCHEMA
    if object_type == BP_OBSERVATION_OBJECT_TYPE:
        return BP_OBSERVATION_SCHEMA
    if object_type == BP_OBSERVER_OBJECT_TYPE:
        return BP_OBSERVER_SCHEMA
    if object_type == BP_ONTOLOGY_OBJECT_TYPE:
        return BP_ONTOLOGY_SCHEMA
    if object_type == BP_ORGANISATION_OBJECT_TYPE:
        return BP_ORGANISATION_SCHEMA
    if object_type == BP_POLICY_OBJECT_TYPE:
        return BP_POLICY_SCHEMA
    if object_type == BP_REMS_OBJECT_TYPE:
        return BP_REMS_SCHEMA
    if object_type == BP_STAINING_OBJECT_TYPE:
        return BP_STAINING_SCHEMA

    raise ValueError(f"Unknown schema for object type: {object_type}")


def _xml_identifier_path_bp(
    schema_type: str,
    root_path: str,
    *,
    title_path: str | None = None,
    description_path: str | None = None,
) -> XmlObjectPaths:
    object_type = _get_xml_object_type_bp(root_path)

    is_mandatory = object_type in BP_MANDATORY_OBJECT_TYPES
    is_single = object_type in BP_SINGLE_OBJECT_TYPES

    return XmlObjectPaths(
        schema_type=schema_type,
        object_type=_get_xml_object_type_bp(root_path),
        root_path=root_path,
        is_mandatory=is_mandatory,
        is_single=is_single,
        identifier_paths=[XmlIdentifierPath(id_path="/@accession", name_path="/@alias")],
        title_path=title_path,
        description_path=description_path,
    )


def _xml_ref_path_bp(
    schema_type: str, root_path: str, rel_ref_path: str, ref_schema_type: str, ref_root_path: str
) -> XmlReferencePaths:
    return XmlReferencePaths(
        schema_type=schema_type,
        ref_schema_type=ref_schema_type,
        object_type=_get_xml_object_type_bp(root_path),
        ref_object_type=_get_xml_object_type_bp(ref_root_path),
        root_path=root_path + "/" + rel_ref_path,
        ref_root_path=ref_root_path,
        paths=[XmlIdentifierPath(id_path="@accession", name_path="@alias")],
    )


def _bp_xml_object_config(version: BigpictureVersion) -> XmlObjectConfig:
    """
    Return the XML processing configuration for a Bigpicture metadata version.

    :param version: The Bigpicture metadata version.
    :returns: The XML processing configuration.
    """
    v2 = version == BigpictureVersion.V2_0
    v3 = version == BigpictureVersion.V3_0

    schema_paths = [
        xml_schema_path(*BP_ANNOTATION_SCHEMA_AND_PATH, BP_ANNOTATION_SET_PATH),
        xml_schema_path(*BP_DATASET_SCHEMA_AND_PATH, BP_DATASET_SET_PATH),
        xml_schema_path(*BP_IMAGE_SCHEMA_AND_PATH, BP_IMAGE_SET_PATH),
        xml_schema_path(*BP_LANDING_PAGE_SCHEMA_AND_PATH, BP_LANDING_PAGE_SET_PATH),
        xml_schema_path(*BP_OBSERVATION_SCHEMA_AND_PATH, BP_OBSERVATION_SET_PATH),
        xml_schema_path(*BP_OBSERVER_SCHEMA_AND_PATH, BP_OBSERVER_SET_PATH),
        xml_schema_path(*BP_ORGANISATION_SCHEMA_AND_PATH, BP_ORGANISATION_SET_PATH),
        xml_schema_path(*BP_POLICY_SCHEMA_AND_PATH, BP_POLICY_SET_PATH),
        xml_schema_path(*BP_REMS_SCHEMA_AND_PATH, BP_REMS_SET_PATH),
        xml_schema_path(
            BP_SAMPLE_SCHEMA,
            [
                BP_SAMPLE_BIOLOGICAL_BEING_PATH,
                BP_SAMPLE_SLIDE_PATH,
                BP_SAMPLE_SPECIMEN_PATH,
                BP_SAMPLE_BLOCK_PATH,
                BP_SAMPLE_CASE_PATH,
            ],
            BP_SAMPLE_SET_PATH,
        ),
        xml_schema_path(*BP_STAINING_SCHEMA_AND_PATH, BP_STAINING_SET_PATH),
    ]

    object_paths = [
        _xml_identifier_path_bp(*BP_ANNOTATION_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_DATASET_SCHEMA_AND_PATH, title_path="/TITLE", description_path="/DESCRIPTION"),
        _xml_identifier_path_bp(*BP_IMAGE_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_LANDING_PAGE_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_OBSERVER_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_ORGANISATION_SCHEMA_AND_PATH, title_path="/NAME"),
        _xml_identifier_path_bp(*BP_POLICY_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_REMS_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_SAMPLE_SLIDE_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_SAMPLE_BLOCK_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_SAMPLE_CASE_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_STAINING_SCHEMA_AND_PATH),
    ]

    reference_paths = [
        # annotation
        _xml_ref_path_bp(*BP_ANNOTATION_SCHEMA_AND_PATH, "/IMAGE_REF", *BP_IMAGE_SCHEMA_AND_PATH),
        # dataset
        _xml_ref_path_bp(*BP_DATASET_SCHEMA_AND_PATH, "/IMAGE_REF", *BP_IMAGE_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_DATASET_SCHEMA_AND_PATH, "/ANNOTATION_REF", *BP_ANNOTATION_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_DATASET_SCHEMA_AND_PATH, "/OBSERVATION_REF", *BP_OBSERVATION_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_DATASET_SCHEMA_AND_PATH, "/COMPLEMENTS_DATASET_REF", *BP_DATASET_SCHEMA_AND_PATH),
        # image
        _xml_ref_path_bp(*BP_IMAGE_SCHEMA_AND_PATH, "/IMAGE_OF", *BP_SAMPLE_SLIDE_SCHEMA_AND_PATH),
        # observation
        _xml_ref_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH, "/CASE_REF", *BP_SAMPLE_CASE_SCHEMA_AND_PATH),
        _xml_ref_path_bp(
            *BP_OBSERVATION_SCHEMA_AND_PATH, "/BIOLOGICAL_BEING_REF", *BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH
        ),
        _xml_ref_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH, "/SPECIMEN_REF", *BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH, "/BLOCK_REF", *BP_SAMPLE_BLOCK_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH, "/SLIDE_REF", *BP_SAMPLE_SLIDE_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH, "/IMAGE_REF", *BP_IMAGE_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH, "/OBSERVER_REF", *BP_OBSERVER_SCHEMA_AND_PATH),
        # organisation
        _xml_ref_path_bp(*BP_ORGANISATION_SCHEMA_AND_PATH, "/DATASET_REF", *BP_DATASET_SCHEMA_AND_PATH),
        # policy
        _xml_ref_path_bp(*BP_POLICY_SCHEMA_AND_PATH, "/DATASET_REF", *BP_DATASET_SCHEMA_AND_PATH),
        # rems
        _xml_ref_path_bp(*BP_REMS_SCHEMA_AND_PATH, "/DATASET_REF", *BP_DATASET_SCHEMA_AND_PATH),
        # landing page
        _xml_ref_path_bp(*BP_LANDING_PAGE_SCHEMA_AND_PATH, "/DATASET_REF", *BP_DATASET_SCHEMA_AND_PATH),
        # sample
        _xml_ref_path_bp(*BP_SAMPLE_SLIDE_SCHEMA_AND_PATH, "/STAINING_INFORMATION_REF", *BP_STAINING_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_SAMPLE_SLIDE_SCHEMA_AND_PATH, "/CREATED_FROM_REF", *BP_SAMPLE_BLOCK_SCHEMA_AND_PATH),
        _xml_ref_path_bp(
            *BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH, "/EXTRACTED_FROM_REF", *BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH
        ),
        _xml_ref_path_bp(*BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH, "/PART_OF_CASE_REF", *BP_SAMPLE_CASE_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_SAMPLE_BLOCK_SCHEMA_AND_PATH, "/SAMPLED_FROM_REF", *BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH),
        _xml_ref_path_bp(
            *BP_SAMPLE_CASE_SCHEMA_AND_PATH, "/BIOLOGICAL_BEING_REF", *BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH
        ),
    ]

    if v2:
        reference_paths += [
            _xml_ref_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH, "/ANNOTATION_REF", *BP_ANNOTATION_SCHEMA_AND_PATH),
        ]

    if v3:
        schema_paths += [
            xml_schema_path(*BP_ANNOTATION_TASK_SCHEMA_AND_PATH, BP_ANNOTATION_TASK_SET_PATH),
            xml_schema_path(*BP_ANNOTATOR_SCHEMA_AND_PATH, BP_ANNOTATOR_SET_PATH),
            xml_schema_path(*BP_ONTOLOGY_SCHEMA_AND_PATH, BP_ONTOLOGY_SET_PATH),
        ]
        object_paths += [
            _xml_identifier_path_bp(*BP_ANNOTATION_TASK_SCHEMA_AND_PATH),
            _xml_identifier_path_bp(*BP_ANNOTATOR_SCHEMA_AND_PATH),
            _xml_identifier_path_bp(*BP_ONTOLOGY_SCHEMA_AND_PATH),
        ]
        reference_paths += [
            _xml_ref_path_bp(*BP_ANNOTATION_SCHEMA_AND_PATH, "/ANNOTATOR_REF", *BP_ANNOTATOR_SCHEMA_AND_PATH),
            _xml_ref_path_bp(*BP_ANNOTATION_SCHEMA_AND_PATH, "/ONTOLOGY_REF", *BP_ONTOLOGY_SCHEMA_AND_PATH),
            _xml_ref_path_bp(*BP_ANNOTATION_SCHEMA_AND_PATH, "/TASK_REF", *BP_ANNOTATION_TASK_SCHEMA_AND_PATH),
            # The parent annotation must be in the same submission.
            _xml_ref_path_bp(*BP_ANNOTATION_SCHEMA_AND_PATH, "/PARENT_ANNOTATION_REF", *BP_ANNOTATION_SCHEMA_AND_PATH),
            _xml_ref_path_bp(*BP_DATASET_SCHEMA_AND_PATH, "/LANDING_PAGE_REF", *BP_LANDING_PAGE_SCHEMA_AND_PATH),
        ]

    return XmlObjectConfig(
        schema_dir=str(BP_XML_SCHEMA_3_DIR if v3 else BP_XML_SCHEMA_2_DIR),
        schema_file_resolver=lambda schema_type: "BP." + schema_type + ".xsd",
        schema_paths=schema_paths,
        object_paths=object_paths,
        reference_paths=reference_paths,
    )


BP_XML_OBJECT_CONFIG_2 = _bp_xml_object_config(BigpictureVersion.V2_0)
BP_XML_OBJECT_CONFIG_3 = _bp_xml_object_config(BigpictureVersion.V3_0)

BP_XML_OBJECT_CONFIGS = {
    BigpictureVersion.V2_0: BP_XML_OBJECT_CONFIG_2,
    BigpictureVersion.V3_0: BP_XML_OBJECT_CONFIG_3,
}


def get_bp_version_from_documents(xml_docs: Iterable[str | bytes]) -> BigpictureVersion:
    """
    Return the Bigpicture metadata version of the submitted XML documents.

    The version must be declared in dataset METADATA_STANDARD attribute.

    :param xml_docs: The Bigpicture XML documents, excluding the DataCite XML.
    :returns: The Bigpicture metadata standard version.
    :raises UserException: If the dataset or the version is missing, or the version is conflicting
    or not supported.
    """
    versions: set[BigpictureVersion] = set()
    for xml in xml_docs:
        if isinstance(xml, str):
            xml = xml.encode("utf-8")
        try:
            _, root = next(etree.iterparse(BytesIO(xml), events=("start",)))
        except etree.XMLSyntaxError as e:
            raise InvalidDocumentException(str(e)) from e
        if root.tag not in (BP_DATASET_SET_PATH.lstrip("/"), BP_DATASET_PATH.lstrip("/")):
            continue
        versions.add(get_bp_version_from_dataset(XmlProcessor.parse_xml(xml).getroot()))

    if not versions:
        # As the XML documents processor would report it.
        raise UserException(f"Expecting exactly one '{BP_DATASET_OBJECT_TYPE}' metadata object but found 0.")
    if len(versions) > 1:
        raise UserException(f"Conflicting Bigpicture metadata versions: {', '.join(sorted(versions))}.")
    return versions.pop()


def get_bp_version_from_dataset(dataset: Element) -> BigpictureVersion:
    """
    Return the Bigpicture metadata version declared by a dataset XML.

    :param dataset: The DATASET or DATASET_SET element.
    :returns: The Bigpicture metadata standard version.
    :raises UserException: If the version is missing, conflicting or not supported.
    """
    return _parse_bp_version(_extract_bp_version(dataset))


def _extract_bp_version(dataset: Element) -> str:
    """
    Return the METADATA_STANDARD value of a dataset XML.

    :param dataset: The DATASET or DATASET_SET element.
    :returns: The METADATA_STANDARD value.
    :raises UserException: If the value is missing, or there is more than one.
    """
    values = {(e.text or "").strip() for e in dataset.iter("METADATA_STANDARD")}
    if not values:
        raise UserException("Missing Bigpicture metadata standard version in dataset METADATA_STANDARD.")
    if len(values) > 1:
        raise UserException(f"Conflicting Bigpicture metadata standard versions: {', '.join(sorted(values))}.")
    return values.pop()


def _parse_bp_version(value: str) -> BigpictureVersion:
    """
    Return the Bigpicture metadata version of a dataset METADATA_STANDARD value.

    :param value: The METADATA_STANDARD value.
    :returns: The Bigpicture metadata standard version.
    :raises UserException: If the version is not supported.
    """
    match = _BP_METADATA_STANDARD_PATTERN.fullmatch(value)
    if match is None or match.group(1) not in BigpictureVersion:
        supported = ", ".join(f"{v}.x" for v in BigpictureVersion)
        raise UserException(f"Unsupported Bigpicture metadata standard version: {value}. Supported: {supported}.")
    return BigpictureVersion(match.group(1))


async def update_landing_page_xml(
    xml: str | bytes,
    config: XmlObjectConfig,
    *,
    datacite_url: str | None = None,
    rems_url: str | None = None,
) -> str:
    """Update landing page XML and return updated XML.

    :param xml: The landing page XML.
    :param config: The XML processing configuration of the submission's Bigpicture metadata version.
    :param datacite_url: The DataCite URL.
    :param rems_url: The REMS URL.
    :returns: updated landing page XML.
    """
    xml = XmlProcessor.parse_xml(xml)

    processor = XmlObjectProcessor(config, xml)

    root_element = processor.root_element

    if rems_url:
        # Add REMS_ACCESS_LINK after DATASET_REF is missing.
        rems_elem = root_element.find("REMS_ACCESS_LINK")
        if rems_elem is None:
            dataset_ref_elem = root_element.find("DATASET_REF")
            if dataset_ref_elem is None:
                raise ValueError("Missing mandatory DATASET_REF element")

            rems_elem = etree.Element("REMS_ACCESS_LINK")
            rems_elem.text = rems_url
            root_element.insert(root_element.index(dataset_ref_elem) + 1, rems_elem)

    if datacite_url:
        # Add ATTRIBUTES is missing.
        attributes_elem = root_element.find("ATTRIBUTES")
        if attributes_elem is None:
            attributes_elem = etree.Element("ATTRIBUTES")
            root_element.append(attributes_elem)

        # Add STRING_ATTRIBUTE.
        attribute_elem = etree.Element("STRING_ATTRIBUTE")
        attributes_elem.append(attribute_elem)

        # Add TAG.
        tag_elem = etree.Element("TAG")
        tag_elem.text = "doi"
        attribute_elem.append(tag_elem)

        # Add VALUE.
        value_elem = etree.Element("VALUE")
        value_elem.text = datacite_url
        attribute_elem.append(value_elem)

    return XmlProcessor.write_xml(xml)


async def as_xml_set_document(xml_docs: list[str], schema_type: str, config: XmlObjectConfig) -> str:
    """Aggregate XML documents into a properly formatted set element document.

    :param xml_docs: List of XML document strings.
    :param schema_type: XML schema type for the set document.
    :param config: The XML processing configuration of the submission's Bigpicture metadata version.
    :returns: Formatted XML document with set wrapper.
    """

    async def _iter_xml_docs() -> AsyncIterator[str]:
        for xml_doc in xml_docs:
            yield xml_doc

    parts = [
        chunk
        async for chunk in XmlDocumentProcessor.iter_xml_document(
            config,
            _iter_xml_docs(),
            schema_type=schema_type,
        )
    ]

    return b"".join(parts).decode("utf-8")
