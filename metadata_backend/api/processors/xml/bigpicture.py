from pathlib import Path

from lxml import etree
from lxml.etree import _Element as Element  # noqa

from .models import XmlIdentifierPath, XmlObjectConfig, XmlObjectPaths, XmlReferencePaths, xml_schema_path
from .processors import XmlObjectProcessor, XmlProcessor

BP_XML_SCHEMA_DIR = Path(__file__).parent.parent.parent.parent / "schemas" / "xml" / "bigpicture"

# The schema type must match the XML schema file name without the ".xsd" extension.

BP_ANNOTATION_SCHEMA = "annotation"
BP_DATASET_SCHEMA = "dataset"
BP_IMAGE_SCHEMA = "image"
BP_LANDING_PAGE_SCHEMA = "landingpage"
BP_OBSERVATION_SCHEMA = "observation"
BP_OBSERVER_SCHEMA = "observer"
BP_ORGANISATION_SCHEMA = "organisation"
BP_POLICY_SCHEMA = "policy"
BP_REMS_SCHEMA = "rems"
BP_SAMPLE_SCHEMA = "sample"
BP_STAINING_SCHEMA = "staining"

BP_ANNOTATION_PATH = "/ANNOTATION"
BP_DATASET_PATH = "/DATASET"
BP_IMAGE_PATH = "/IMAGE"
BP_LANDING_PAGE_PATH = "/LANDING_PAGE"
BP_OBSERVATION_PATH = "/OBSERVATION"
BP_OBSERVER_PATH = "/OBSERVER"
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
BP_DATASET_SCHEMA_AND_PATH = (BP_DATASET_SCHEMA, BP_DATASET_PATH)
BP_IMAGE_SCHEMA_AND_PATH = (BP_IMAGE_SCHEMA, BP_IMAGE_PATH)
BP_LANDING_PAGE_SCHEMA_AND_PATH = (BP_LANDING_PAGE_SCHEMA, BP_LANDING_PAGE_PATH)
BP_OBSERVATION_SCHEMA_AND_PATH = (BP_OBSERVATION_SCHEMA, BP_OBSERVATION_PATH)
BP_OBSERVER_SCHEMA_AND_PATH = (BP_OBSERVER_SCHEMA, BP_OBSERVER_PATH)
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
BP_DATASET_SET_PATH = "/DATASET_SET"
BP_IMAGE_SET_PATH = "/IMAGE_SET"
BP_LANDING_PAGE_SET_PATH = "/LANDING_PAGE_SET"
BP_OBSERVATION_SET_PATH = "/OBSERVATION_SET"
BP_OBSERVER_SET_PATH = "/OBSERVER_SET"
BP_ORGANISATION_SET_PATH = "/ORGANISATION_SET"
BP_POLICY_SET_PATH = "/POLICY_SET"
BP_REMS_SET_PATH = "/REMS_SET"
BP_SAMPLE_SET_PATH = "/SAMPLE_SET"
BP_STAINING_SET_PATH = "/STAINING_SET"


def _get_xml_object_type_bp(root_path: str) -> str:
    return root_path.lstrip(".").lstrip("/").replace("_", "").lower()


BP_ANNOTATION_OBJECT_TYPE = _get_xml_object_type_bp(BP_ANNOTATION_PATH)
BP_DATASET_OBJECT_TYPE = _get_xml_object_type_bp(BP_DATASET_PATH)
BP_IMAGE_OBJECT_TYPE = _get_xml_object_type_bp(BP_IMAGE_PATH)
BP_LANDING_PAGE_OBJECT_TYPE = _get_xml_object_type_bp(BP_LANDING_PAGE_PATH)
BP_OBSERVATION_OBJECT_TYPE = _get_xml_object_type_bp(BP_OBSERVATION_PATH)
BP_OBSERVER_OBJECT_TYPE = _get_xml_object_type_bp(BP_OBSERVER_PATH)
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

BP_OBJECT_TYPES = [
    BP_ANNOTATION_OBJECT_TYPE,
    BP_DATASET_OBJECT_TYPE,
    BP_IMAGE_OBJECT_TYPE,
    BP_LANDING_PAGE_OBJECT_TYPE,
    BP_OBSERVATION_OBJECT_TYPE,
    BP_OBSERVER_OBJECT_TYPE,
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


def _xml_identifier_path_bp(
    schema_type: str,
    root_path: str,
    *,
    is_mandatory: bool = False,
    is_single: bool = False,
    title_path: str | None = None,
    description_path: str | None = None,
) -> XmlObjectPaths:
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


# BP submission configuration for a full non-incremental submission.
BP_FULL_SUBMISSION_XML_OBJECT_CONFIG = XmlObjectConfig(
    schema_dir=str(BP_XML_SCHEMA_DIR),
    schema_file_resolver=lambda schema_type: "BP." + schema_type + ".xsd",
    schema_paths=[
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
    ],
    object_paths=[
        _xml_identifier_path_bp(*BP_ANNOTATION_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(
            *BP_DATASET_SCHEMA_AND_PATH,
            is_mandatory=True,
            is_single=True,
            title_path="/TITLE",
            description_path="/DESCRIPTION",
        ),
        _xml_identifier_path_bp(*BP_IMAGE_SCHEMA_AND_PATH, is_mandatory=True),
        _xml_identifier_path_bp(*BP_LANDING_PAGE_SCHEMA_AND_PATH, is_mandatory=True, is_single=True),
        _xml_identifier_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH, is_mandatory=True),
        _xml_identifier_path_bp(*BP_OBSERVER_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(
            *BP_ORGANISATION_SCHEMA_AND_PATH, is_mandatory=True, is_single=True, title_path="/NAME"
        ),
        _xml_identifier_path_bp(*BP_POLICY_SCHEMA_AND_PATH, is_mandatory=True, is_single=True),
        _xml_identifier_path_bp(*BP_REMS_SCHEMA_AND_PATH, is_mandatory=True, is_single=True),
        _xml_identifier_path_bp(*BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_SAMPLE_SLIDE_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_SAMPLE_BLOCK_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_SAMPLE_CASE_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_STAINING_SCHEMA_AND_PATH, is_mandatory=True),
    ],
    reference_paths=[
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
        _xml_ref_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH, "/ANNOTATION_REF", *BP_ANNOTATION_SCHEMA_AND_PATH),
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
    ],
)


def update_landing_page_xml(xml: str | bytes, *, datacite_url: str | None = None, rems_url: str | None = None) -> str:
    """
    Update landing page XML and return updated XML.

    :param xml: The landing page XML.
    :param datacite_url: The DataCite URL.
    :param rems_url: The REMS URL.
    :returns: updated landing page XML.
    """
    xml = XmlProcessor.parse_xml(xml)

    processor = XmlObjectProcessor(BP_FULL_SUBMISSION_XML_OBJECT_CONFIG, xml)

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
