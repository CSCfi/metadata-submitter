from pathlib import Path

from lxml import etree
from lxml.etree import _Element as Element  # noqa

from .models import XmlIdentifierPath, XmlObjectConfig, XmlObjectPaths, XmlReferencePaths, xml_schema_path

FEGA_XML_SCHEMA_DIR = Path(__file__).parent.parent.parent.parent / "schemas" / "xml" / "fega"

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
    schema_dir=str(FEGA_XML_SCHEMA_DIR),
    schema_file_resolver=fega_schema_file_resolver,
    schema_paths=[
        xml_schema_path(*FEGA_DAC_SCHEMA_AND_PATH, FEGA_DAC_SET_PATH),
        xml_schema_path(*FEGA_DATASET_SCHEMA_AND_PATH, FEGA_DATASET_SET_PATH),
        xml_schema_path(*FEGA_ANALYSIS_SCHEMA_AND_PATH, FEGA_ANALYSIS_SET_PATH),
        xml_schema_path(*FEGA_EXPERIMENT_SCHEMA_AND_PATH, FEGA_EXPERIMENT_SET_PATH),
        xml_schema_path(*FEGA_RUN_SCHEMA_AND_PATH, FEGA_RUN_SET_PATH),
        xml_schema_path(*FEGA_SAMPLE_SCHEMA_AND_PATH, FEGA_SAMPLE_SET_PATH),
        xml_schema_path(*FEGA_STUDY_SCHEMA_AND_PATH, FEGA_STUDY_SET_PATH),
        xml_schema_path(*FEGA_POLICY_SCHEMA_AND_PATH, FEGA_POLICY_SET_PATH),
        xml_schema_path(*FEGA_SUBMISSION_SCHEMA_AND_PATH, FEGA_SUBMISSION_SET_PATH),
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
