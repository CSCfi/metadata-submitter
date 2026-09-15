import re
import uuid

import pytest

from metadata_backend.api.exceptions import UserException
from metadata_backend.api.processors.models import ObjectIdentifier
from metadata_backend.api.processors.xml.bigpicture import (
    BP_ANNOTATION_PATH,
    BP_ANNOTATION_SCHEMA,
    BP_ANNOTATION_SCHEMA_AND_PATH,
    BP_ANNOTATION_SET_PATH,
    BP_DATASET_PATH,
    BP_DATASET_SCHEMA,
    BP_DATASET_SCHEMA_AND_PATH,
    BP_IMAGE_PATH,
    BP_IMAGE_SCHEMA,
    BP_IMAGE_SCHEMA_AND_PATH,
    BP_LANDING_PAGE_PATH,
    BP_LANDING_PAGE_SCHEMA,
    BP_LANDING_PAGE_SCHEMA_AND_PATH,
    BP_OBSERVATION_PATH,
    BP_OBSERVATION_SCHEMA,
    BP_OBSERVATION_SCHEMA_AND_PATH,
    BP_OBSERVER_PATH,
    BP_OBSERVER_SCHEMA,
    BP_OBSERVER_SCHEMA_AND_PATH,
    BP_ORGANISATION_PATH,
    BP_ORGANISATION_SCHEMA,
    BP_ORGANISATION_SCHEMA_AND_PATH,
    BP_POLICY_PATH,
    BP_POLICY_SCHEMA,
    BP_POLICY_SCHEMA_AND_PATH,
    BP_REMS_PATH,
    BP_REMS_SCHEMA,
    BP_REMS_SCHEMA_AND_PATH,
    BP_SAMPLE_BIOLOGICAL_BEING_PATH,
    BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH,
    BP_SAMPLE_BLOCK_PATH,
    BP_SAMPLE_BLOCK_SCHEMA_AND_PATH,
    BP_SAMPLE_CASE_PATH,
    BP_SAMPLE_CASE_SCHEMA_AND_PATH,
    BP_SAMPLE_SCHEMA,
    BP_SAMPLE_SET_PATH,
    BP_SAMPLE_SLIDE_PATH,
    BP_SAMPLE_SLIDE_SCHEMA_AND_PATH,
    BP_SAMPLE_SPECIMEN_PATH,
    BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH,
    BP_STAINING_PATH,
    BP_STAINING_SCHEMA,
    BP_STAINING_SCHEMA_AND_PATH,
    BP_XML_OBJECT_CONFIG,
    _get_xml_object_type_bp,
    as_xml_set_document,
    update_landing_page_xml,
)
from metadata_backend.api.processors.xml.processors import (
    XmlFileDocumentsProcessor,
    XmlObjectProcessor,
    XmlStringDocumentsProcessor,
)
from metadata_backend.api.services.submission.bigpicture import (
    BP_FILES,
    BigpictureObjectSubmissionService,
)
from metadata_backend.api.services.submission.bigpicture_attributes import (
    BP_ATTRIBUTE_TYPE_STRING,
    BigpictureAttributesConfig,
    BigpictureStringAttribute,
)

from .test_utils import TEST_FILES_DIR, assert_object, assert_ref, assert_ref_length

SUBMISSION_DIR = TEST_FILES_DIR / "xml" / "bigpicture"


def create_xml_object_identifier_bp(schema_type: str, root_path: str, name: str, id: str):
    return ObjectIdentifier(
        schema_type=schema_type, object_type=_get_xml_object_type_bp(root_path), root_path=root_path, name=name, id=id
    )


async def test_bp_submission():
    """Test self-contained BP submission with alias references."""

    processor = XmlFileDocumentsProcessor(
        BP_XML_OBJECT_CONFIG,
        str(SUBMISSION_DIR),
        [
            "dataset.xml",
            "policy.xml",
            "image.xml",
            "annotation.xml",
            "observation.xml",
            "observer.xml",
            "sample.xml",
            "staining.xml",
            "landing_page.xml",
            "rems.xml",
            "organisation.xml",
        ],
    )

    annotation_name = "1"
    dataset_name = "1"
    image_name = "1"
    observation_name = "1"
    observer_name = "1"
    policy_name = "1"
    sample_biological_being_name = "1"
    sample_case_name = "1"
    sample_specimen_name = "1"
    sample_block_name = "1"
    sample_slide_name = "1"
    staining_name = "1"
    landing_page_name = "1"
    organisation_name = "1"
    rems_name = "1"

    # Test configuration with annotation and sample
    config = BP_XML_OBJECT_CONFIG
    annotation_object_type = _get_xml_object_type_bp(BP_ANNOTATION_PATH)
    assert config.get_root_path(annotation_object_type) == BP_ANNOTATION_PATH
    assert config.get_set_path(object_type=annotation_object_type) == BP_ANNOTATION_SET_PATH
    assert config.get_set_path(schema_type=BP_ANNOTATION_SCHEMA) == BP_ANNOTATION_SET_PATH
    assert config.get_object_type(BP_ANNOTATION_PATH) == annotation_object_type
    assert config.get_schema_type(annotation_object_type) == BP_ANNOTATION_SCHEMA
    assert config.get_object_types(BP_ANNOTATION_SCHEMA) == [annotation_object_type]

    sample_object_type = _get_xml_object_type_bp(BP_SAMPLE_CASE_PATH)
    assert config.get_root_path(sample_object_type) == BP_SAMPLE_CASE_PATH
    assert config.get_set_path(object_type=sample_object_type) == BP_SAMPLE_SET_PATH
    assert config.get_set_path(schema_type=BP_SAMPLE_SCHEMA) == BP_SAMPLE_SET_PATH
    assert config.get_object_type(BP_SAMPLE_CASE_PATH) == sample_object_type
    assert config.get_schema_type(sample_object_type) == BP_SAMPLE_SCHEMA
    assert sample_object_type in config.get_object_types(BP_SAMPLE_SCHEMA)
    assert len(config.get_object_types(BP_SAMPLE_SCHEMA)) == 5

    # Assert not accessioned state
    #

    # Annotation
    assert_object(processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, None)
    assert_ref_length(processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, 1)
    assert_ref(processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, BP_IMAGE_SCHEMA_AND_PATH, image_name, None)
    # Dataset
    assert_object(
        processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, None, title="test_title", description="test_description"
    )
    assert_ref_length(processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, 3)
    assert_ref(processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, BP_IMAGE_SCHEMA_AND_PATH, image_name, None)
    assert_ref(
        processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, None
    )
    assert_ref(
        processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, BP_OBSERVATION_SCHEMA_AND_PATH, observation_name, None
    )
    # Image
    assert_object(processor, BP_IMAGE_SCHEMA_AND_PATH, image_name, None)
    assert_ref_length(processor, BP_IMAGE_SCHEMA_AND_PATH, image_name, 1)
    assert_ref(
        processor, BP_IMAGE_SCHEMA_AND_PATH, image_name, BP_SAMPLE_SLIDE_SCHEMA_AND_PATH, sample_slide_name, None
    )
    # Observation
    assert_object(processor, BP_OBSERVATION_SCHEMA_AND_PATH, observation_name, None)
    assert_ref_length(processor, BP_OBSERVATION_SCHEMA_AND_PATH, observation_name, 2)
    assert_ref(
        processor,
        BP_OBSERVATION_SCHEMA_AND_PATH,
        observation_name,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        annotation_name,
        None,
    )
    assert_ref(
        processor, BP_OBSERVATION_SCHEMA_AND_PATH, observation_name, BP_OBSERVER_SCHEMA_AND_PATH, observer_name, None
    )
    # Observer
    assert_object(processor, BP_OBSERVER_SCHEMA_AND_PATH, observer_name, None)
    assert_ref_length(processor, BP_OBSERVER_SCHEMA_AND_PATH, observer_name, 0)
    # Policy
    assert_object(processor, BP_POLICY_SCHEMA_AND_PATH, policy_name, None)
    assert_ref_length(processor, BP_POLICY_SCHEMA_AND_PATH, policy_name, 1)
    assert_ref(processor, BP_POLICY_SCHEMA_AND_PATH, policy_name, BP_DATASET_SCHEMA_AND_PATH, dataset_name, None)
    # Sample
    assert_object(processor, BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH, sample_biological_being_name, None)
    assert_object(processor, BP_SAMPLE_CASE_SCHEMA_AND_PATH, sample_case_name, None)
    assert_object(processor, BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH, sample_specimen_name, None)
    assert_object(processor, BP_SAMPLE_BLOCK_SCHEMA_AND_PATH, sample_block_name, None)
    assert_object(processor, BP_SAMPLE_SLIDE_SCHEMA_AND_PATH, sample_slide_name, None)
    assert_ref_length(processor, BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH, sample_biological_being_name, 0)
    assert_ref_length(processor, BP_SAMPLE_CASE_SCHEMA_AND_PATH, sample_case_name, 1)
    assert_ref(
        processor,
        BP_SAMPLE_CASE_SCHEMA_AND_PATH,
        sample_case_name,
        BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH,
        sample_biological_being_name,
        None,
    )
    assert_ref_length(processor, BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH, sample_specimen_name, 2)
    assert_ref(
        processor,
        BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH,
        sample_specimen_name,
        BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH,
        sample_biological_being_name,
        None,
    )
    assert_ref(
        processor,
        BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH,
        sample_specimen_name,
        BP_SAMPLE_CASE_SCHEMA_AND_PATH,
        sample_case_name,
        None,
    )
    assert_ref_length(processor, BP_SAMPLE_BLOCK_SCHEMA_AND_PATH, sample_block_name, 1)
    assert_ref(
        processor,
        BP_SAMPLE_BLOCK_SCHEMA_AND_PATH,
        sample_block_name,
        BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH,
        sample_specimen_name,
        None,
    )
    assert_ref_length(processor, BP_SAMPLE_SLIDE_SCHEMA_AND_PATH, sample_slide_name, 2)
    assert_ref(
        processor,
        BP_SAMPLE_SLIDE_SCHEMA_AND_PATH,
        sample_slide_name,
        BP_SAMPLE_BLOCK_SCHEMA_AND_PATH,
        sample_block_name,
        None,
    )
    assert_ref(
        processor, BP_SAMPLE_SLIDE_SCHEMA_AND_PATH, sample_slide_name, BP_STAINING_SCHEMA_AND_PATH, staining_name, None
    )
    # Staining
    assert_object(processor, BP_STAINING_SCHEMA_AND_PATH, staining_name, None)
    assert_ref_length(processor, BP_STAINING_SCHEMA_AND_PATH, staining_name, 0)
    # Landing page
    assert_object(processor, BP_LANDING_PAGE_SCHEMA_AND_PATH, landing_page_name, None)
    assert_ref_length(processor, BP_LANDING_PAGE_SCHEMA_AND_PATH, landing_page_name, 1)
    assert_ref(
        processor, BP_LANDING_PAGE_SCHEMA_AND_PATH, landing_page_name, BP_DATASET_SCHEMA_AND_PATH, dataset_name, None
    )
    # Organisation
    assert_object(processor, BP_ORGANISATION_SCHEMA_AND_PATH, organisation_name, None, title="test_name")
    assert_ref_length(processor, BP_ORGANISATION_SCHEMA_AND_PATH, organisation_name, 1)
    assert_ref(
        processor, BP_ORGANISATION_SCHEMA_AND_PATH, organisation_name, BP_DATASET_SCHEMA_AND_PATH, dataset_name, None
    )
    # Rems
    assert_object(processor, BP_REMS_SCHEMA_AND_PATH, rems_name, None)
    assert_ref_length(processor, BP_REMS_SCHEMA_AND_PATH, rems_name, 1)
    assert_ref(processor, BP_REMS_SCHEMA_AND_PATH, rems_name, BP_DATASET_SCHEMA_AND_PATH, dataset_name, None)

    # Assign accessions
    #

    # Annotation
    annotation_id = f"annotation_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_bp(BP_ANNOTATION_SCHEMA, BP_ANNOTATION_PATH, annotation_name, annotation_id)
    )
    # Dataset
    dataset_id = f"dataset_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_bp(BP_DATASET_SCHEMA, BP_DATASET_PATH, dataset_name, dataset_id)
    )
    # Image
    image_id = f"image_{str(uuid.uuid4())}"
    processor.set_object_id(create_xml_object_identifier_bp(BP_IMAGE_SCHEMA, BP_IMAGE_PATH, image_name, image_id))
    # Observation
    observation_id = f"observation_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_bp(BP_OBSERVATION_SCHEMA, BP_OBSERVATION_PATH, observation_name, observation_id)
    )
    # Observer
    observer_id = f"observer_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_bp(BP_OBSERVER_SCHEMA, BP_OBSERVER_PATH, observer_name, observer_id)
    )
    # Policy
    policy_id = f"policy_{str(uuid.uuid4())}"
    processor.set_object_id(create_xml_object_identifier_bp(BP_POLICY_SCHEMA, BP_POLICY_PATH, policy_name, policy_id))
    # Staining
    staining_id = f"staining_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_bp(BP_STAINING_SCHEMA, BP_STAINING_PATH, staining_name, staining_id)
    )
    # Landing page
    landing_page_id = f"landing_page_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_bp(
            BP_LANDING_PAGE_SCHEMA, BP_LANDING_PAGE_PATH, landing_page_name, landing_page_id
        )
    )
    # Sample
    sample_biological_being_id = f"sample_biological_being_{str(uuid.uuid4())}"
    sample_case_id = f"sample_case_{str(uuid.uuid4())}"
    sample_specimen_id = f"sample_specimen_{str(uuid.uuid4())}"
    sample_block_id = f"sample_block_{str(uuid.uuid4())}"
    sample_slide_id = f"sample_slide_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_bp(
            BP_SAMPLE_SCHEMA, BP_SAMPLE_BIOLOGICAL_BEING_PATH, sample_biological_being_name, sample_biological_being_id
        )
    )
    processor.set_object_id(
        create_xml_object_identifier_bp(BP_SAMPLE_SCHEMA, BP_SAMPLE_CASE_PATH, sample_case_name, sample_case_id)
    )
    processor.set_object_id(
        create_xml_object_identifier_bp(
            BP_SAMPLE_SCHEMA, BP_SAMPLE_SPECIMEN_PATH, sample_specimen_name, sample_specimen_id
        )
    )
    processor.set_object_id(
        create_xml_object_identifier_bp(BP_SAMPLE_SCHEMA, BP_SAMPLE_BLOCK_PATH, sample_block_name, sample_block_id)
    )
    processor.set_object_id(
        create_xml_object_identifier_bp(BP_SAMPLE_SCHEMA, BP_SAMPLE_SLIDE_PATH, sample_slide_name, sample_slide_id)
    )
    # Organisation
    organisation_id = f"organisation_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_bp(
            BP_ORGANISATION_SCHEMA, BP_ORGANISATION_PATH, organisation_name, organisation_id
        )
    )
    # Rems
    rems_id = f"rems_{str(uuid.uuid4())}"
    processor.set_object_id(create_xml_object_identifier_bp(BP_REMS_SCHEMA, BP_REMS_PATH, rems_name, rems_id))

    # Assert accessioned state
    #

    # Annotation
    assert_object(processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, annotation_id)
    assert_ref_length(processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, 1)
    assert_ref(
        processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, BP_IMAGE_SCHEMA_AND_PATH, image_name, image_id
    )
    # Dataset
    assert_object(processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, dataset_id)
    assert_ref_length(processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, 3)
    assert_ref(processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, BP_IMAGE_SCHEMA_AND_PATH, image_name, image_id)
    assert_ref(
        processor,
        BP_DATASET_SCHEMA_AND_PATH,
        dataset_name,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        annotation_name,
        annotation_id,
    )
    assert_ref(
        processor,
        BP_DATASET_SCHEMA_AND_PATH,
        dataset_name,
        BP_OBSERVATION_SCHEMA_AND_PATH,
        observation_name,
        observation_id,
    )
    # Image
    assert_object(processor, BP_IMAGE_SCHEMA_AND_PATH, image_name, image_id)
    assert_ref_length(processor, BP_IMAGE_SCHEMA_AND_PATH, image_name, 1)
    assert_ref(
        processor,
        BP_IMAGE_SCHEMA_AND_PATH,
        image_name,
        BP_SAMPLE_SLIDE_SCHEMA_AND_PATH,
        sample_slide_name,
        sample_slide_id,
    )
    # Observation
    assert_object(processor, BP_OBSERVATION_SCHEMA_AND_PATH, observation_name, observation_id)
    assert_ref_length(processor, BP_OBSERVATION_SCHEMA_AND_PATH, observation_name, 2)
    assert_ref(
        processor,
        BP_OBSERVATION_SCHEMA_AND_PATH,
        observation_name,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        annotation_name,
        annotation_id,
    )
    assert_ref(
        processor,
        BP_OBSERVATION_SCHEMA_AND_PATH,
        observation_name,
        BP_OBSERVER_SCHEMA_AND_PATH,
        observer_name,
        observer_id,
    )
    # Observer
    assert_object(processor, BP_OBSERVER_SCHEMA_AND_PATH, observer_name, observer_id)
    assert_ref_length(processor, BP_OBSERVER_SCHEMA_AND_PATH, observer_name, 0)
    # Policy
    assert_object(processor, BP_POLICY_SCHEMA_AND_PATH, policy_name, policy_id)
    assert_ref_length(processor, BP_POLICY_SCHEMA_AND_PATH, policy_name, 1)
    assert_ref(processor, BP_POLICY_SCHEMA_AND_PATH, policy_name, BP_DATASET_SCHEMA_AND_PATH, dataset_name, dataset_id)
    # Sample
    assert_object(
        processor, BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH, sample_biological_being_name, sample_biological_being_id
    )
    assert_object(processor, BP_SAMPLE_CASE_SCHEMA_AND_PATH, sample_case_name, sample_case_id)
    assert_object(processor, BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH, sample_specimen_name, sample_specimen_id)
    assert_object(processor, BP_SAMPLE_BLOCK_SCHEMA_AND_PATH, sample_block_name, sample_block_id)
    assert_object(processor, BP_SAMPLE_SLIDE_SCHEMA_AND_PATH, sample_slide_name, sample_slide_id)
    assert_ref_length(processor, BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH, sample_biological_being_name, 0)
    assert_ref_length(processor, BP_SAMPLE_CASE_SCHEMA_AND_PATH, sample_case_name, 1)
    assert_ref(
        processor,
        BP_SAMPLE_CASE_SCHEMA_AND_PATH,
        sample_case_name,
        BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH,
        sample_biological_being_name,
        sample_biological_being_id,
    )
    assert_ref_length(processor, BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH, sample_specimen_name, 2)
    assert_ref(
        processor,
        BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH,
        sample_specimen_name,
        BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH,
        sample_biological_being_name,
        sample_biological_being_id,
    )
    assert_ref(
        processor,
        BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH,
        sample_specimen_name,
        BP_SAMPLE_CASE_SCHEMA_AND_PATH,
        sample_case_name,
        sample_case_id,
    )
    assert_ref_length(processor, BP_SAMPLE_BLOCK_SCHEMA_AND_PATH, sample_block_name, 1)
    assert_ref(
        processor,
        BP_SAMPLE_BLOCK_SCHEMA_AND_PATH,
        sample_block_name,
        BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH,
        sample_specimen_name,
        sample_specimen_id,
    )
    assert_ref_length(processor, BP_SAMPLE_SLIDE_SCHEMA_AND_PATH, sample_slide_name, 2)
    assert_ref(
        processor,
        BP_SAMPLE_SLIDE_SCHEMA_AND_PATH,
        sample_slide_name,
        BP_SAMPLE_BLOCK_SCHEMA_AND_PATH,
        sample_block_name,
        sample_block_id,
    )
    assert_ref(
        processor,
        BP_SAMPLE_SLIDE_SCHEMA_AND_PATH,
        sample_slide_name,
        BP_STAINING_SCHEMA_AND_PATH,
        staining_name,
        staining_id,
    )
    # Staining
    assert_object(processor, BP_STAINING_SCHEMA_AND_PATH, staining_name, staining_id)
    assert_ref_length(processor, BP_STAINING_SCHEMA_AND_PATH, staining_name, 0)
    # Landing page
    assert_object(processor, BP_LANDING_PAGE_SCHEMA_AND_PATH, landing_page_name, landing_page_id)
    assert_ref_length(processor, BP_LANDING_PAGE_SCHEMA_AND_PATH, landing_page_name, 1)
    assert_ref(
        processor,
        BP_LANDING_PAGE_SCHEMA_AND_PATH,
        landing_page_name,
        BP_DATASET_SCHEMA_AND_PATH,
        dataset_name,
        dataset_id,
    )
    # Organisation
    assert_object(processor, BP_ORGANISATION_SCHEMA_AND_PATH, organisation_name, organisation_id)
    assert_ref_length(processor, BP_ORGANISATION_SCHEMA_AND_PATH, organisation_name, 1)
    assert_ref(
        processor,
        BP_ORGANISATION_SCHEMA_AND_PATH,
        organisation_name,
        BP_DATASET_SCHEMA_AND_PATH,
        dataset_name,
        dataset_id,
    )
    # Rems
    assert_object(processor, BP_REMS_SCHEMA_AND_PATH, rems_name, rems_id)
    assert_ref_length(processor, BP_REMS_SCHEMA_AND_PATH, rems_name, 1)
    assert_ref(processor, BP_REMS_SCHEMA_AND_PATH, rems_name, BP_DATASET_SCHEMA_AND_PATH, dataset_name, dataset_id)


def _bp_object_xml(*attributes: tuple[str, str], set_attributes: tuple[tuple[str, str], ...] = ()) -> str:
    """A Bigpicture metadata object with the given attributes."""

    def string_attribute(tag: str, value: str) -> str:
        return f"<STRING_ATTRIBUTE><TAG>{tag}</TAG><VALUE>{value}</VALUE></STRING_ATTRIBUTE>"

    tags = "".join(string_attribute(tag, value) for tag, value in attributes)
    tags += "".join(
        f"<SET_ATTRIBUTE><TAG>{tag}s</TAG><VALUE>{string_attribute(tag, value)}</VALUE></SET_ATTRIBUTE>"
        for tag, value in set_attributes
    )
    return f'<POLICY alias="1"><DATASET_REF alias="1"/><ATTRIBUTES>{tags}</ATTRIBUTES></POLICY>'


def _bp_object_processor(
    *attributes: tuple[str, str], set_attributes: tuple[tuple[str, str], ...] = ()
) -> XmlObjectProcessor:
    return XmlObjectProcessor(BP_XML_OBJECT_CONFIG, _bp_object_xml(*attributes, set_attributes=set_attributes))


def _string_attribute(tag: str, **fields) -> BigpictureStringAttribute:
    return BigpictureStringAttribute(tag=tag, attribute_type=BP_ATTRIBUTE_TYPE_STRING, **fields)


def _attributes_config(
    attributes: tuple[BigpictureStringAttribute, ...] = (),
    set_attributes: tuple[BigpictureStringAttribute, ...] = (),
) -> BigpictureAttributesConfig:
    return BigpictureAttributesConfig(attributes=attributes, set_attributes=set_attributes)


_OBJECT_NAME = "Policy"


async def test_update_landing_page_xml():
    xml = """<LANDING_PAGE alias="1">
  <DATASET_REF alias="1"/>
  <ATTRIBUTES>
    <STRING_ATTRIBUTE>
      <TAG>test</TAG>
      <VALUE>test</VALUE>
    </STRING_ATTRIBUTE>
  </ATTRIBUTES>
</LANDING_PAGE>
"""
    datacite_url = "TEST_DATACITE_URL"
    rems_url = "TEST_REMS_URL"

    expected_xml = f"""<LANDING_PAGE alias="1">
  <DATASET_REF alias="1"/>
  <REMS_ACCESS_LINK>{rems_url}</REMS_ACCESS_LINK>
  <ATTRIBUTES>
    <STRING_ATTRIBUTE>
      <TAG>test</TAG>
      <VALUE>test</VALUE>
    </STRING_ATTRIBUTE>
    <STRING_ATTRIBUTE>
      <TAG>doi</TAG>
      <VALUE>{datacite_url}</VALUE>
    </STRING_ATTRIBUTE>
  </ATTRIBUTES>
</LANDING_PAGE>
"""

    assert expected_xml == await update_landing_page_xml(xml, datacite_url=datacite_url, rems_url=rems_url)


async def test_as_xml_set_document_single_document():
    """Test aggregating a single XML document into a set element."""
    xml = """<DATASET alias="dataset_1" accession="BPDST001">
  <TITLE>Test Dataset</TITLE>
  <DESCRIPTION>A test dataset</DESCRIPTION>
</DATASET>"""

    expected_xml = """<?xml version='1.0' encoding='UTF-8'?>
<DATASET_SET>
  <DATASET alias="dataset_1" accession="BPDST001">
    <TITLE>Test Dataset</TITLE>
    <DESCRIPTION>A test dataset</DESCRIPTION>
  </DATASET>
</DATASET_SET>
"""

    assert expected_xml == await as_xml_set_document([xml], BP_DATASET_SCHEMA)


async def test_as_xml_set_document_single_object_type():
    """Test aggregating XML documents with a single object type into a set element."""
    xml1 = """<ANNOTATION alias="ann_1" accession="BPANN001">
  <DESCRIPTION>Annotation 1</DESCRIPTION>
</ANNOTATION>"""
    xml2 = """<ANNOTATION alias="ann_2" accession="BPANN002">
  <DESCRIPTION>Annotation 2</DESCRIPTION>
</ANNOTATION>"""

    expected_xml = """<?xml version='1.0' encoding='UTF-8'?>
<ANNOTATION_SET>
  <ANNOTATION alias="ann_1" accession="BPANN001">
    <DESCRIPTION>Annotation 1</DESCRIPTION>
  </ANNOTATION>
  <ANNOTATION alias="ann_2" accession="BPANN002">
    <DESCRIPTION>Annotation 2</DESCRIPTION>
  </ANNOTATION>
</ANNOTATION_SET>
"""

    assert expected_xml == await as_xml_set_document([xml1, xml2], BP_ANNOTATION_SCHEMA)


async def test_as_xml_set_document_tuple_object_type():
    """Test aggregating XML documents with tuple object type (sample types) into a set element."""
    xml1 = """<BIOLOGICAL_BEING alias="bb_1" accession="BPBB001">
  <DESCRIPTION>Biological Being 1</DESCRIPTION>
</BIOLOGICAL_BEING>"""
    xml2 = """<SLIDE alias="slide_1" accession="BPSLD001">
  <DESCRIPTION>Slide 1</DESCRIPTION>
</SLIDE>"""

    expected_xml = """<?xml version='1.0' encoding='UTF-8'?>
<SAMPLE_SET>
  <BIOLOGICAL_BEING alias="bb_1" accession="BPBB001">
    <DESCRIPTION>Biological Being 1</DESCRIPTION>
  </BIOLOGICAL_BEING>
  <SLIDE alias="slide_1" accession="BPSLD001">
    <DESCRIPTION>Slide 1</DESCRIPTION>
  </SLIDE>
</SAMPLE_SET>
"""

    assert expected_xml == await as_xml_set_document([xml1, xml2], BP_SAMPLE_SCHEMA)


def _bp_submission_service() -> BigpictureObjectSubmissionService:
    """A submission service wired with nothing, as validate_documents uses no service."""

    return BigpictureObjectSubmissionService(None, None, None, None)  # type: ignore[arg-type]


def _bp_documents_processor(*, exclude: str | None = None, **policy_values: str) -> XmlStringDocumentsProcessor:
    """A processor over the whole Bigpicture document set.

    :param exclude: A document left out of the submission.
    :param policy_values: New values for the named policy STRING_ATTRIBUTE tags.
    """

    documents = []
    for name in BP_FILES:
        path = SUBMISSION_DIR / name
        if name == exclude or not path.is_file():
            continue
        document = path.read_text(encoding="utf-8")
        if name == "policy.xml":
            for tag, value in policy_values.items():
                document, count = re.subn(
                    rf"(<TAG>{tag}</TAG>\s*<VALUE>)[^<]*(</VALUE>)", rf"\g<1>{value}\g<2>", document
                )
                assert count == 1, f"'{tag}' is given {count} times in {name} rather than once"
        documents.append(document)

    return XmlStringDocumentsProcessor(BP_XML_OBJECT_CONFIG, documents)


def test_validate_documents_accepts_the_whole_document_set():
    """The document set the policy tests alter passes validation unaltered, so a failure
    below is the alteration rather than the fixture."""

    service = _bp_submission_service()
    service._processor = _bp_documents_processor()

    service.validate_documents()


def test_validate_documents_reports_a_policy_the_license_cannot_be_created_from():
    """A submitter is told what is wrong with the policy when submitting it, not later
    when publishing."""

    service = _bp_submission_service()
    service._processor = _bp_documents_processor(defined_research_question_required="Maybe")

    with pytest.raises(UserException, match="defined_research_question_required"):
        service.validate_documents()


def test_bp_documents_reject_a_missing_mandatory_metadata_object():
    """A sample document is mandatory for each of the four sample object types that are,
    which the XML documents processor enforces per object type rather than per schema.

    Reported before any policy problem, since the processor cannot even be built.
    """

    with pytest.raises(ValueError, match="metadata object but found 0"):
        _bp_documents_processor(exclude="sample.xml", defined_research_question_required="Maybe")
