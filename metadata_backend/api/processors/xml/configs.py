"""Xml processor configurations."""

from pathlib import Path

from lxml import etree
from lxml.etree import _Element as Element  # noqa

from metadata_backend.api.processors.xml.models import (
    XmlIdentifierPath,
    XmlObjectConfig,
    XmlObjectPaths,
    XmlReferencePaths,
    XmlSchemaPath,
)

XML_SCHEMA_DIR = Path(__file__).parent.parent.parent.parent / "helpers" / "schemas"


def _xml_schema_path(schema_type: str, root_paths: str | list[str], set_path: str) -> XmlSchemaPath:
    if isinstance(root_paths, str):
        root_paths = [root_paths]
    return XmlSchemaPath(set_path=set_path, schema_type=schema_type, root_paths=root_paths)


# BP
#

# The schema type must match the XML schema file name without the ".xsd" extension.

BP_ANNOTATION_SCHEMA = "bpannotation"
BP_DATASET_SCHEMA = "bpdataset"
BP_IMAGE_SCHEMA = "bpimage"
BP_LANDING_PAGE_SCHEMA = "bplandingpage"
BP_OBSERVATION_SCHEMA = "bpobservation"
BP_OBSERVER_SCHEMA = "bpobserver"
BP_ORGANISATION_SCHEMA = "bporganisation"
BP_POLICY_SCHEMA = "bppolicy"
BP_REMS_SCHEMA = "bprems"
BP_SAMPLE_SCHEMA = "bpsample"
BP_STAINING_SCHEMA = "bpstaining"

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
    schema_dir=str(XML_SCHEMA_DIR),
    schema_file_resolver=lambda schema_type: "BP." + schema_type + ".xsd",
    schema_paths=[
        _xml_schema_path(*BP_ANNOTATION_SCHEMA_AND_PATH, BP_ANNOTATION_SET_PATH),
        _xml_schema_path(*BP_DATASET_SCHEMA_AND_PATH, BP_DATASET_SET_PATH),
        _xml_schema_path(*BP_IMAGE_SCHEMA_AND_PATH, BP_IMAGE_SET_PATH),
        _xml_schema_path(*BP_LANDING_PAGE_SCHEMA_AND_PATH, BP_LANDING_PAGE_SET_PATH),
        _xml_schema_path(*BP_OBSERVATION_SCHEMA_AND_PATH, BP_OBSERVATION_SET_PATH),
        _xml_schema_path(*BP_OBSERVER_SCHEMA_AND_PATH, BP_OBSERVER_SET_PATH),
        _xml_schema_path(*BP_ORGANISATION_SCHEMA_AND_PATH, BP_ORGANISATION_SET_PATH),
        _xml_schema_path(*BP_POLICY_SCHEMA_AND_PATH, BP_POLICY_SET_PATH),
        _xml_schema_path(*BP_REMS_SCHEMA_AND_PATH, BP_REMS_SET_PATH),
        _xml_schema_path(
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
        _xml_schema_path(*BP_STAINING_SCHEMA_AND_PATH, BP_STAINING_SET_PATH),
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
        # TODO(improve): _xml_identifier_path_bp(*BP_DATACITE_SCHEMA_AND_PATH, is_single=True),
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

# FEGA
#

# The schema type must match the XML schema file name without the ".xsd" extension.

FEGA_DAC_SCHEMA = "dac"
FEGA_DATASET_SCHEMA = "dataset"
FEGA_ANALYSIS_SCHEMA = "analysis"
FEGA_EXPERIMENT_SCHEMA = "experiment"
FEGA_RUN_SCHEMA = "run"
FEGA_SAMPLE_SCHEMA = "sample"
FEGA_STUDY_SCHEMA = "study"
FEGA_POLICY_SCHEMA = "policy"
FEGA_SUBMISSION_SCHEMA = "submission"

FEGA_DAC_PATH = "/DAC"
FEGA_DATASET_PATH = "/DATASET"
FEGA_ANALYSIS_PATH = "/ANALYSIS"
FEGA_EXPERIMENT_PATH = "/EXPERIMENT"
FEGA_RUN_PATH = "/RUN"
FEGA_SAMPLE_PATH = "/SAMPLE"
FEGA_STUDY_PATH = "/STUDY"
FEGA_POLICY_PATH = "/POLICY"
FEGA_SUBMISSION_PATH = "/SUBMISSION"

FEGA_DAC_SCHEMA_AND_PATH = (FEGA_DAC_SCHEMA, FEGA_DAC_PATH)
FEGA_DATASET_SCHEMA_AND_PATH = (FEGA_DATASET_SCHEMA, FEGA_DATASET_PATH)
FEGA_ANALYSIS_SCHEMA_AND_PATH = (FEGA_ANALYSIS_SCHEMA, FEGA_ANALYSIS_PATH)
FEGA_EXPERIMENT_SCHEMA_AND_PATH = (FEGA_EXPERIMENT_SCHEMA, FEGA_EXPERIMENT_PATH)
FEGA_RUN_SCHEMA_AND_PATH = (FEGA_RUN_SCHEMA, FEGA_RUN_PATH)
FEGA_SAMPLE_SCHEMA_AND_PATH = (FEGA_SAMPLE_SCHEMA, FEGA_SAMPLE_PATH)
FEGA_STUDY_SCHEMA_AND_PATH = (FEGA_STUDY_SCHEMA, FEGA_STUDY_PATH)
FEGA_POLICY_SCHEMA_AND_PATH = (FEGA_POLICY_SCHEMA, FEGA_POLICY_PATH)
FEGA_SUBMISSION_SCHEMA_AND_PATH = (FEGA_SUBMISSION_SCHEMA, FEGA_SUBMISSION_PATH)

FEGA_DAC_SET_PATH = "/DAC_SET"
FEGA_DATASET_SET_PATH = "/DATASETS"
FEGA_ANALYSIS_SET_PATH = "/ANALYSIS_SET"
FEGA_EXPERIMENT_SET_PATH = "/EXPERIMENT_SET"
FEGA_RUN_SET_PATH = "/RUN_SET"
FEGA_SAMPLE_SET_PATH = "/SAMPLE_SET"
FEGA_STUDY_SET_PATH = "/STUDY_SET"
FEGA_POLICY_SET_PATH = "/POLICY_SET"
FEGA_SUBMISSION_SET_PATH = "/SUBMISSION_SET"


def _id_insertion_callback_fega(node: Element) -> Element:
    # Add IDENTIFIERS element as the first element.
    identifiers_element = node.find("IDENTIFIERS")
    if identifiers_element is None:
        identifiers_element = etree.Element("IDENTIFIERS")
        node.insert(0, identifiers_element)
    # Add PRIMARY_ID element as the first element.
    primary_id_element = identifiers_element.find("PRIMARY_ID")
    if primary_id_element is None:
        primary_id_element = etree.Element("PRIMARY_ID")
        identifiers_element.insert(0, primary_id_element)
    return primary_id_element


def _name_insertion_callback_fega(node: Element) -> Element:
    # Add IDENTIFIERS element as the first element.
    identifiers_element = node.find("IDENTIFIERS")
    if identifiers_element is None:
        identifiers_element = etree.Element("IDENTIFIERS")
        node.insert(0, identifiers_element)
    # Add SUBMITTER_ID element as the first child element of IDENTIFIERS element
    # after EXTERNAL_ID if it exists, or after SECONDARY_ID if it exists, or after
    # PRIMARY_ID if it exists. Otherwise, add it as the first element.

    submitter_id_element = etree.Element("SUBMITTER_ID")

    inserted = False
    for insert_after_element_name in ["EXTERNAL_ID", "SECONDARY_ID", "PRIMARY_ID"]:
        insert_after_element = identifiers_element.find(insert_after_element_name)
        if insert_after_element is not None:
            index = identifiers_element.index(insert_after_element)
            identifiers_element.insert(index + 1, submitter_id_element)
            inserted = True
            break
    if not inserted:
        identifiers_element.insert(0, submitter_id_element)

    return submitter_id_element


def _get_xml_object_type_fega(root_path: str) -> str:
    return root_path.lstrip(".").lstrip("/").lower()


def _xml_identifier_path_fega(
    schema_type: str,
    root_path: str,
    is_mandatory: bool = False,
    is_single: bool = False,
    title_path: str | None = None,
    description_path: str | None = None,
) -> XmlObjectPaths:
    return XmlObjectPaths(
        schema_type=schema_type,
        object_type=_get_xml_object_type_fega(root_path),
        root_path=root_path,
        is_mandatory=is_mandatory,
        is_single=is_single,
        identifier_paths=[
            XmlIdentifierPath(id_path="/@accession", name_path="/@alias"),
            XmlIdentifierPath(
                id_path="IDENTIFIERS/PRIMARY_ID",
                name_path="IDENTIFIERS/SUBMITTER_ID",
                id_insertion_callback=_id_insertion_callback_fega,
                name_insertion_callback=_name_insertion_callback_fega,
            ),
        ],
        title_path=title_path,
        description_path=description_path,
    )


def _xml_ref_path_fega(
    schema_type: str, root_path: str, rel_ref_path: str, ref_schema_type: str, ref_root_path: str
) -> XmlReferencePaths:
    return XmlReferencePaths(
        schema_type=schema_type,
        ref_schema_type=ref_schema_type,
        object_type=_get_xml_object_type_fega(root_path),
        ref_object_type=_get_xml_object_type_fega(ref_root_path),
        root_path=root_path + "/" + rel_ref_path,
        ref_root_path=ref_root_path,
        paths=[
            XmlIdentifierPath(id_path="@accession", name_path="@refname"),
            XmlIdentifierPath(
                id_path="@IDENTIFIERS/PRIMARY_ID",
                name_path="IDENTIFIERS/SUBMITTER_ID",
                id_insertion_callback=_id_insertion_callback_fega,
                name_insertion_callback=_name_insertion_callback_fega,
            ),
        ],
    )


def fega_schema_file_resolver(schema_type: str) -> str:
    """
    Return the name of the FEGA XML schema file.

    :param schema_type: The schema type.
    :return: The name of the FEGA XML schema file.
    """

    if schema_type in (FEGA_DAC_SCHEMA, FEGA_DATASET_SCHEMA, FEGA_POLICY_SCHEMA):
        return "EGA." + schema_type + ".xsd"
    return "SRA." + schema_type + ".xsd"


# FEGA submission configuration for a full non-incremental submission.
FEGA_FULL_SUBMISSION_XML_OBJECT_CONFIG = XmlObjectConfig(
    schema_dir=str(XML_SCHEMA_DIR),
    schema_file_resolver=fega_schema_file_resolver,
    schema_paths=[
        _xml_schema_path(*FEGA_DAC_SCHEMA_AND_PATH, FEGA_DAC_SET_PATH),
        _xml_schema_path(*FEGA_DATASET_SCHEMA_AND_PATH, FEGA_DATASET_SET_PATH),
        _xml_schema_path(*FEGA_ANALYSIS_SCHEMA_AND_PATH, FEGA_ANALYSIS_SET_PATH),
        _xml_schema_path(*FEGA_EXPERIMENT_SCHEMA_AND_PATH, FEGA_EXPERIMENT_SET_PATH),
        _xml_schema_path(*FEGA_RUN_SCHEMA_AND_PATH, FEGA_RUN_SET_PATH),
        _xml_schema_path(*FEGA_SAMPLE_SCHEMA_AND_PATH, FEGA_SAMPLE_SET_PATH),
        _xml_schema_path(*FEGA_STUDY_SCHEMA_AND_PATH, FEGA_STUDY_SET_PATH),
        _xml_schema_path(*FEGA_POLICY_SCHEMA_AND_PATH, FEGA_POLICY_SET_PATH),
        _xml_schema_path(*FEGA_SUBMISSION_SCHEMA_AND_PATH, FEGA_SUBMISSION_SET_PATH),
    ],
    object_paths=[
        _xml_identifier_path_fega(*FEGA_DAC_SCHEMA_AND_PATH, title_path="/TITLE"),
        _xml_identifier_path_fega(
            *FEGA_DATASET_SCHEMA_AND_PATH,
            is_mandatory=True,
            is_single=True,
            title_path="/TITLE",
            description_path="/DESCRIPTION",
        ),
        _xml_identifier_path_fega(*FEGA_ANALYSIS_SCHEMA_AND_PATH, title_path="/TITLE", description_path="/DESCRIPTION"),
        _xml_identifier_path_fega(*FEGA_EXPERIMENT_SCHEMA_AND_PATH, title_path="/TITLE"),
        _xml_identifier_path_fega(*FEGA_RUN_SCHEMA_AND_PATH, title_path="/TITLE"),
        _xml_identifier_path_fega(*FEGA_SAMPLE_SCHEMA_AND_PATH, title_path="/TITLE", description_path="/DESCRIPTION"),
        _xml_identifier_path_fega(
            *FEGA_STUDY_SCHEMA_AND_PATH,
            title_path="/DESCRIPTOR/STUDY_TITLE",
            description_path="(/DESCRIPTOR/STUDY_DESCRIPTION | /DESCRIPTOR/STUDY_ABSTRACT)[1]",
        ),
        _xml_identifier_path_fega(*FEGA_POLICY_SCHEMA_AND_PATH, title_path="/TITLE"),
        _xml_identifier_path_fega(*FEGA_SUBMISSION_SCHEMA_AND_PATH, title_path="/TITLE"),
    ],
    reference_paths=[
        # DAC
        # dataset
        _xml_ref_path_fega(*FEGA_DATASET_SCHEMA_AND_PATH, "RUN_REF", *FEGA_RUN_SCHEMA_AND_PATH),
        _xml_ref_path_fega(*FEGA_DATASET_SCHEMA_AND_PATH, "ANALYSIS_REF", *FEGA_ANALYSIS_SCHEMA_AND_PATH),
        _xml_ref_path_fega(*FEGA_DATASET_SCHEMA_AND_PATH, "POLICY_REF", *FEGA_POLICY_SCHEMA_AND_PATH),
        # analysis
        _xml_ref_path_fega(*FEGA_ANALYSIS_SCHEMA_AND_PATH, "STUDY_REF", *FEGA_STUDY_SCHEMA_AND_PATH),
        _xml_ref_path_fega(*FEGA_ANALYSIS_SCHEMA_AND_PATH, "SAMPLE_REF", *FEGA_SAMPLE_SCHEMA_AND_PATH),
        _xml_ref_path_fega(*FEGA_ANALYSIS_SCHEMA_AND_PATH, "EXPERIMENT_REF", *FEGA_EXPERIMENT_SCHEMA_AND_PATH),
        _xml_ref_path_fega(*FEGA_ANALYSIS_SCHEMA_AND_PATH, "RUN_REF", *FEGA_RUN_SCHEMA_AND_PATH),
        _xml_ref_path_fega(*FEGA_ANALYSIS_SCHEMA_AND_PATH, "ANALYSIS_REF", *FEGA_ANALYSIS_SCHEMA_AND_PATH),
        # experiment
        _xml_ref_path_fega(*FEGA_EXPERIMENT_SCHEMA_AND_PATH, "STUDY_REF", *FEGA_STUDY_SCHEMA_AND_PATH),
        _xml_ref_path_fega(*FEGA_EXPERIMENT_SCHEMA_AND_PATH, "DESIGN/SAMPLE_DESCRIPTOR", *FEGA_SAMPLE_SCHEMA_AND_PATH),
        # run
        _xml_ref_path_fega(*FEGA_RUN_SCHEMA_AND_PATH, "EXPERIMENT_REF", *FEGA_EXPERIMENT_SCHEMA_AND_PATH),
        # sample
        # study
        # policy
        _xml_ref_path_fega(*FEGA_POLICY_SCHEMA_AND_PATH, "DAC_REF", *FEGA_DAC_SCHEMA_AND_PATH),
        # submission
    ],
)
