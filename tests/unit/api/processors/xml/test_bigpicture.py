import re
import uuid
from pathlib import Path

import pytest

from metadata_backend.api.exceptions import UserException
from metadata_backend.api.processors.exceptions import InvalidDocumentException
from metadata_backend.api.processors.models import ObjectIdentifier
from metadata_backend.api.processors.xml.bigpicture import (
    BP_ANNOTATION_PATH,
    BP_ANNOTATION_SCHEMA,
    BP_ANNOTATION_SCHEMA_AND_PATH,
    BP_ANNOTATION_SET_PATH,
    BP_ANNOTATION_TASK_PATH,
    BP_ANNOTATION_TASK_SCHEMA,
    BP_ANNOTATION_TASK_SCHEMA_AND_PATH,
    BP_ANNOTATION_TASK_SET_PATH,
    BP_ANNOTATOR_PATH,
    BP_ANNOTATOR_SCHEMA,
    BP_ANNOTATOR_SCHEMA_AND_PATH,
    BP_ANNOTATOR_SET_PATH,
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
    BP_ONTOLOGY_PATH,
    BP_ONTOLOGY_SCHEMA,
    BP_ONTOLOGY_SCHEMA_AND_PATH,
    BP_ONTOLOGY_SET_PATH,
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
    BP_XML_OBJECT_CONFIG_2,
    BP_XML_OBJECT_CONFIG_3,
    BP_XML_SCHEMA_3_DIR,
    BigpictureVersion,
    _get_xml_object_type_bp,
    as_xml_set_document,
    get_bp_version_from_dataset,
    get_bp_version_from_documents,
    update_landing_page_xml,
)
from metadata_backend.api.processors.xml.exceptions import SchemaValidationException
from metadata_backend.api.processors.xml.processors import (
    XmlFileDocumentsProcessor,
    XmlObjectProcessor,
    XmlProcessor,
    XmlStringDocumentsProcessor,
)
from metadata_backend.api.services.submission.bigpicture import (
    BP_FILES,
    BigpictureObjectSubmissionService,
)
from metadata_backend.api.services.submission.bigpicture_attributes import (
    BP_ATTRIBUTE_TYPE_STRING,
    BigpictureAttributesConfig,
    BigpictureVersionedStringAttribute,
)
from metadata_backend.api.services.submission.submission import ObjectSubmission
from tests.utils import (
    BP_ANNOTATION_1_FILE,
    BP_ANNOTATION_2_FILE,
    BP_ANNOTATION_TASK_FILE,
    BP_IMAGE_1_FILE,
    BP_IMAGE_2_FILE,
    BP_ONTOLOGY_FILE,
)

from .test_utils import TEST_FILES_DIR, assert_object, assert_ref, assert_ref_length

SUBMISSION_2_DIR = TEST_FILES_DIR / "xml" / "bigpicture" / "2.0"
SUBMISSION_3_DIR = TEST_FILES_DIR / "xml" / "bigpicture" / "3.0"


def create_xml_object_identifier_bp(schema_type: str, root_path: str, name: str, id: str):
    return ObjectIdentifier(
        schema_type=schema_type, object_type=_get_xml_object_type_bp(root_path), root_path=root_path, name=name, id=id
    )


async def test_bp_submission_v2():
    """Test self-contained BP 2.0 metadata submission with alias references."""

    processor = XmlFileDocumentsProcessor(
        BP_XML_OBJECT_CONFIG_2,
        str(SUBMISSION_2_DIR),
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
    config = BP_XML_OBJECT_CONFIG_2
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


async def test_bp_submission_v3():
    """Test self-contained BP 3.0 metadata submission with alias references.

    includes the annotator, ontology and annotation task objects, the annotation references
    to them and to a parent annotation, and the dataset reference to the landing page.
    The observation no longer references an annotation.
    """

    processor = XmlFileDocumentsProcessor(
        BP_XML_OBJECT_CONFIG_3,
        str(SUBMISSION_3_DIR),
        [
            "dataset.xml",
            "policy.xml",
            "image.xml",
            "annotation.xml",
            "annotator.xml",
            "ontology.xml",
            "annotation_task.xml",
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
    child_annotation_name = "2"  # The parent annotation is annotation_name.
    annotator_name = "1"
    ontology_name = "1"
    annotation_task_name = "1"
    dataset_name = "1"
    image_name = "1"
    second_image_name = "2"  # The image of child_annotation_name.
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

    # Test configuration with annotation, sample and the objects introduced in 3.0
    config = BP_XML_OBJECT_CONFIG_3
    assert config.schema_dir == str(BP_XML_SCHEMA_3_DIR)

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

    for schema_type, root_path, set_path in (
        (BP_ANNOTATOR_SCHEMA, BP_ANNOTATOR_PATH, BP_ANNOTATOR_SET_PATH),
        (BP_ONTOLOGY_SCHEMA, BP_ONTOLOGY_PATH, BP_ONTOLOGY_SET_PATH),
        (BP_ANNOTATION_TASK_SCHEMA, BP_ANNOTATION_TASK_PATH, BP_ANNOTATION_TASK_SET_PATH),
    ):
        object_type = _get_xml_object_type_bp(root_path)
        assert config.get_root_path(object_type) == root_path
        assert config.get_set_path(object_type=object_type) == set_path
        assert config.get_set_path(schema_type=schema_type) == set_path
        assert config.get_object_type(root_path) == object_type
        assert config.get_schema_type(object_type) == schema_type
        assert config.get_object_types(schema_type) == [object_type]

    # Assert not accessioned state
    #

    # Annotation
    assert_object(processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, None)
    assert_ref_length(processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, 4)
    assert_ref(processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, BP_IMAGE_SCHEMA_AND_PATH, image_name, None)
    assert_ref(
        processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, BP_ANNOTATOR_SCHEMA_AND_PATH, annotator_name, None
    )
    assert_ref(
        processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, BP_ONTOLOGY_SCHEMA_AND_PATH, ontology_name, None
    )
    assert_ref(
        processor,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        annotation_name,
        BP_ANNOTATION_TASK_SCHEMA_AND_PATH,
        annotation_task_name,
        None,
    )
    # Child annotation
    assert_object(processor, BP_ANNOTATION_SCHEMA_AND_PATH, child_annotation_name, None)
    assert_ref_length(processor, BP_ANNOTATION_SCHEMA_AND_PATH, child_annotation_name, 5)
    assert_ref(
        processor,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        child_annotation_name,
        BP_IMAGE_SCHEMA_AND_PATH,
        second_image_name,
        None,
    )
    assert_ref(
        processor,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        child_annotation_name,
        BP_ANNOTATOR_SCHEMA_AND_PATH,
        annotator_name,
        None,
    )
    assert_ref(
        processor,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        child_annotation_name,
        BP_ONTOLOGY_SCHEMA_AND_PATH,
        ontology_name,
        None,
    )
    assert_ref(
        processor,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        child_annotation_name,
        BP_ANNOTATION_TASK_SCHEMA_AND_PATH,
        annotation_task_name,
        None,
    )
    assert_ref(
        processor,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        child_annotation_name,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        annotation_name,
        None,
    )
    # Annotator
    assert_object(processor, BP_ANNOTATOR_SCHEMA_AND_PATH, annotator_name, None)
    assert_ref_length(processor, BP_ANNOTATOR_SCHEMA_AND_PATH, annotator_name, 0)
    # Ontology
    assert_object(processor, BP_ONTOLOGY_SCHEMA_AND_PATH, ontology_name, None)
    assert_ref_length(processor, BP_ONTOLOGY_SCHEMA_AND_PATH, ontology_name, 0)
    # Annotation task
    assert_object(processor, BP_ANNOTATION_TASK_SCHEMA_AND_PATH, annotation_task_name, None)
    assert_ref_length(processor, BP_ANNOTATION_TASK_SCHEMA_AND_PATH, annotation_task_name, 0)
    # Dataset
    assert_object(
        processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, None, title="test_title", description="test_description"
    )
    assert_ref_length(processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, 5)
    assert_ref(processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, BP_IMAGE_SCHEMA_AND_PATH, image_name, None)
    assert_ref(
        processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, None
    )
    assert_ref(
        processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, BP_ANNOTATION_SCHEMA_AND_PATH, child_annotation_name, None
    )
    assert_ref(
        processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, BP_OBSERVATION_SCHEMA_AND_PATH, observation_name, None
    )
    assert_ref(
        processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, BP_LANDING_PAGE_SCHEMA_AND_PATH, landing_page_name, None
    )
    # Image
    assert_object(processor, BP_IMAGE_SCHEMA_AND_PATH, image_name, None)
    assert_ref_length(processor, BP_IMAGE_SCHEMA_AND_PATH, image_name, 1)
    assert_ref(
        processor, BP_IMAGE_SCHEMA_AND_PATH, image_name, BP_SAMPLE_SLIDE_SCHEMA_AND_PATH, sample_slide_name, None
    )
    # Observation: references the image and the observer, and no longer an annotation.
    assert_object(processor, BP_OBSERVATION_SCHEMA_AND_PATH, observation_name, None)
    assert_ref_length(processor, BP_OBSERVATION_SCHEMA_AND_PATH, observation_name, 2)
    assert_ref(processor, BP_OBSERVATION_SCHEMA_AND_PATH, observation_name, BP_IMAGE_SCHEMA_AND_PATH, image_name, None)
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
    # Child annotation
    child_annotation_id = f"annotation_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_bp(
            BP_ANNOTATION_SCHEMA, BP_ANNOTATION_PATH, child_annotation_name, child_annotation_id
        )
    )
    # Annotator
    annotator_id = f"annotator_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_bp(BP_ANNOTATOR_SCHEMA, BP_ANNOTATOR_PATH, annotator_name, annotator_id)
    )
    # Ontology
    ontology_id = f"ontology_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_bp(BP_ONTOLOGY_SCHEMA, BP_ONTOLOGY_PATH, ontology_name, ontology_id)
    )
    # Annotation task
    annotation_task_id = f"annotation_task_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_bp(
            BP_ANNOTATION_TASK_SCHEMA, BP_ANNOTATION_TASK_PATH, annotation_task_name, annotation_task_id
        )
    )
    # Dataset
    dataset_id = f"dataset_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_bp(BP_DATASET_SCHEMA, BP_DATASET_PATH, dataset_name, dataset_id)
    )
    # Image
    image_id = f"image_{str(uuid.uuid4())}"
    processor.set_object_id(create_xml_object_identifier_bp(BP_IMAGE_SCHEMA, BP_IMAGE_PATH, image_name, image_id))
    second_image_id = f"image_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_bp(BP_IMAGE_SCHEMA, BP_IMAGE_PATH, second_image_name, second_image_id)
    )
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
    assert_ref_length(processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, 4)
    assert_ref(
        processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, BP_IMAGE_SCHEMA_AND_PATH, image_name, image_id
    )
    assert_ref(
        processor,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        annotation_name,
        BP_ANNOTATOR_SCHEMA_AND_PATH,
        annotator_name,
        annotator_id,
    )
    assert_ref(
        processor,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        annotation_name,
        BP_ONTOLOGY_SCHEMA_AND_PATH,
        ontology_name,
        ontology_id,
    )
    assert_ref(
        processor,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        annotation_name,
        BP_ANNOTATION_TASK_SCHEMA_AND_PATH,
        annotation_task_name,
        annotation_task_id,
    )
    # Child annotation
    assert_object(processor, BP_ANNOTATION_SCHEMA_AND_PATH, child_annotation_name, child_annotation_id)
    assert_ref_length(processor, BP_ANNOTATION_SCHEMA_AND_PATH, child_annotation_name, 5)
    assert_ref(
        processor,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        child_annotation_name,
        BP_IMAGE_SCHEMA_AND_PATH,
        second_image_name,
        second_image_id,
    )
    assert_ref(
        processor,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        child_annotation_name,
        BP_ANNOTATOR_SCHEMA_AND_PATH,
        annotator_name,
        annotator_id,
    )
    assert_ref(
        processor,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        child_annotation_name,
        BP_ONTOLOGY_SCHEMA_AND_PATH,
        ontology_name,
        ontology_id,
    )
    assert_ref(
        processor,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        child_annotation_name,
        BP_ANNOTATION_TASK_SCHEMA_AND_PATH,
        annotation_task_name,
        annotation_task_id,
    )
    assert_ref(
        processor,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        child_annotation_name,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        annotation_name,
        annotation_id,
    )
    # Annotator
    assert_object(processor, BP_ANNOTATOR_SCHEMA_AND_PATH, annotator_name, annotator_id)
    assert_ref_length(processor, BP_ANNOTATOR_SCHEMA_AND_PATH, annotator_name, 0)
    # Ontology
    assert_object(processor, BP_ONTOLOGY_SCHEMA_AND_PATH, ontology_name, ontology_id)
    assert_ref_length(processor, BP_ONTOLOGY_SCHEMA_AND_PATH, ontology_name, 0)
    # Annotation task
    assert_object(processor, BP_ANNOTATION_TASK_SCHEMA_AND_PATH, annotation_task_name, annotation_task_id)
    assert_ref_length(processor, BP_ANNOTATION_TASK_SCHEMA_AND_PATH, annotation_task_name, 0)
    # Dataset
    assert_object(processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, dataset_id)
    assert_ref_length(processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, 5)
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
        BP_ANNOTATION_SCHEMA_AND_PATH,
        child_annotation_name,
        child_annotation_id,
    )
    assert_ref(
        processor,
        BP_DATASET_SCHEMA_AND_PATH,
        dataset_name,
        BP_OBSERVATION_SCHEMA_AND_PATH,
        observation_name,
        observation_id,
    )
    assert_ref(
        processor,
        BP_DATASET_SCHEMA_AND_PATH,
        dataset_name,
        BP_LANDING_PAGE_SCHEMA_AND_PATH,
        landing_page_name,
        landing_page_id,
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
        BP_IMAGE_SCHEMA_AND_PATH,
        image_name,
        image_id,
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


def _bp_objects(
    submission_dir: Path, filenames: list[str] = BP_FILES, **replacements: tuple[str, str]
) -> list[ObjectSubmission]:
    """The Bigpicture XML files of a directory as submitted objects.

    :param submission_dir: The directory of the XML files.
    :param filenames: The XML files, those missing from the directory skipped. All Bigpicture
        XML files by default.
    :param replacements: The old and new text replaced in the XML file named by the key, without
        its ".xml" extension.
    """

    objects = []
    for name in filenames:
        path = submission_dir / name
        if not path.is_file():
            continue
        document = path.read_text(encoding="utf-8")
        if name.removesuffix(".xml") in replacements:
            old, new = replacements[name.removesuffix(".xml")]
            assert old in document
            document = document.replace(old, new)
        objects.append(ObjectSubmission(filename=name, document=document))
    return objects


def test_bp_submission_3_is_processed_with_the_3_configuration():
    processor, _, _ = BigpictureObjectSubmissionService._create_processor(_bp_objects(SUBMISSION_3_DIR))

    assert processor.xml_processors[0].config is BP_XML_OBJECT_CONFIG_3


def test_bp_submission_2_is_processed_with_the_2_configuration():
    processor, _, _ = BigpictureObjectSubmissionService._create_processor(_bp_objects(SUBMISSION_2_DIR))

    assert processor.xml_processors[0].config is BP_XML_OBJECT_CONFIG_2


def test_bp_submission_2_rejects_a_3_file():
    """A 2.0 submission cannot contain a file introduced in 3.0: the 2.0 configuration does not
    have its object type."""

    objects = _bp_objects(SUBMISSION_2_DIR) + _bp_objects(SUBMISSION_3_DIR, ["annotator.xml"])

    with pytest.raises(InvalidDocumentException, match="Unknown object type for root path: /ANNOTATOR_SET"):
        BigpictureObjectSubmissionService._create_processor(objects)


@pytest.mark.parametrize(
    ("submission_dir", "filenames", "replacements", "error"),
    [
        # An observation cannot reference an annotation in 3.0.
        (
            SUBMISSION_3_DIR,
            BP_FILES,
            {"observation": ('<IMAGE_REF alias="1"/>', '<ANNOTATION_REF alias="1"/>')},
            "ANNOTATION_REF': This element is not expected",
        ),
        # An annotation must reference an annotator in 3.0.
        (
            SUBMISSION_3_DIR,
            BP_FILES,
            {
                "annotation": (
                    '<ANNOTATOR_REF alias="1"/>\n        <ONTOLOGY_REF alias="1"/>',
                    '<ONTOLOGY_REF alias="1"/>',
                )
            },
            "ONTOLOGY_REF': This element is not expected. Expected is \\( ANNOTATOR_REF \\)",
        ),
        # An annotation must reference an ontology in 3.0: the reference is not nillable.
        (
            SUBMISSION_3_DIR,
            BP_FILES,
            {
                "annotation": (
                    '<ONTOLOGY_REF alias="1"/>',
                    '<ONTOLOGY_REF xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:nil="true"/>',
                )
            },
            "ONTOLOGY_REF': The element is not 'nillable'",
        ),
        # A dataset must have a description in 3.0.
        (
            SUBMISSION_3_DIR,
            BP_FILES,
            {"dataset": ("<DESCRIPTION>test_description</DESCRIPTION>", "")},
            "VERSION': This element is not expected. Expected is \\( DESCRIPTION \\)",
        ),
        # 2.0 documents declared as 3.0 are validated against the 3.0 schemas.
        (
            SUBMISSION_2_DIR,
            BP_FILES,
            {"dataset": ("<METADATA_STANDARD>2.0.0<", "<METADATA_STANDARD>3.0.0<")},
            "XML Schema validation failed",
        ),
        # 3.0 documents declared as 2.0 are validated against the 2.0 schemas. Without the files
        # introduced in 3.0, which the 2.0 configuration rejects before validating any schema.
        (
            SUBMISSION_3_DIR,
            [f for f in BP_FILES if f not in ("annotation_task.xml", "annotator.xml", "ontology.xml")],
            {"dataset": ("<METADATA_STANDARD>3.0.0<", "<METADATA_STANDARD>2.0.0<")},
            "XML Schema validation failed",
        ),
    ],
    ids=[
        "observation-annotation-ref",
        "annotation-without-annotator",
        "annotation-nil-ontology",
        "dataset-without-description",
        "2.0-declared-3.0",
        "3.0-declared-2.0",
    ],
)
def test_bp_submission_schema_validation_follows_the_declared_version(submission_dir, filenames, replacements, error):
    with pytest.raises(SchemaValidationException, match=error):
        BigpictureObjectSubmissionService._create_processor(_bp_objects(submission_dir, filenames, **replacements))


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
    # BP.policy.xsd has not changed between 2.0 and 3.0.
    return XmlObjectProcessor(BP_XML_OBJECT_CONFIG_2, _bp_object_xml(*attributes, set_attributes=set_attributes))


def _string_attribute(tag: str, **fields) -> BigpictureVersionedStringAttribute:
    return BigpictureVersionedStringAttribute(tag=tag, attribute_type=BP_ATTRIBUTE_TYPE_STRING, **fields)


def _attributes_config(
    attributes: tuple[BigpictureVersionedStringAttribute, ...] = (),
    set_attributes: tuple[BigpictureVersionedStringAttribute, ...] = (),
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

    # BP.landing_page.xsd has not changed between 2.0 and 3.0.
    assert expected_xml == await update_landing_page_xml(
        xml, BP_XML_OBJECT_CONFIG_2, datacite_url=datacite_url, rems_url=rems_url
    )


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

    # The set elements have not changed between 2.0 and 3.0, and the documents are not validated.
    assert expected_xml == await as_xml_set_document([xml], BP_DATASET_SCHEMA, BP_XML_OBJECT_CONFIG_2)


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

    # The set elements have not changed between 2.0 and 3.0, and the documents are not validated.
    assert expected_xml == await as_xml_set_document([xml1, xml2], BP_ANNOTATION_SCHEMA, BP_XML_OBJECT_CONFIG_2)


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

    # The set elements have not changed between 2.0 and 3.0, and the documents are not validated.
    assert expected_xml == await as_xml_set_document([xml1, xml2], BP_SAMPLE_SCHEMA, BP_XML_OBJECT_CONFIG_2)


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
        path = SUBMISSION_2_DIR / name
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

    return XmlStringDocumentsProcessor(BP_XML_OBJECT_CONFIG_2, documents)


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

    with pytest.raises(InvalidDocumentException, match="metadata object but found 0"):
        _bp_documents_processor(exclude="sample.xml", defined_research_question_required="Maybe")


@pytest.mark.parametrize(
    ("xml_docs", "expected_version"),
    [
        (
            ["<DATASET_SET><DATASET><METADATA_STANDARD>2.0.0</METADATA_STANDARD></DATASET></DATASET_SET>"],
            BigpictureVersion.V2_0,
        ),
        (
            ["<DATASET_SET><DATASET><METADATA_STANDARD>2.0.12</METADATA_STANDARD></DATASET></DATASET_SET>"],
            BigpictureVersion.V2_0,
        ),
        (
            ["<DATASET_SET><DATASET><METADATA_STANDARD>3.0.0</METADATA_STANDARD></DATASET></DATASET_SET>"],
            BigpictureVersion.V3_0,
        ),
        (
            ["<DATASET_SET><DATASET><METADATA_STANDARD> 3.0.1 </METADATA_STANDARD></DATASET></DATASET_SET>"],
            BigpictureVersion.V3_0,
        ),
        (
            [b"<DATASET_SET><DATASET><METADATA_STANDARD>3.0.0</METADATA_STANDARD></DATASET></DATASET_SET>"],
            BigpictureVersion.V3_0,
        ),
        (["<DATASET><METADATA_STANDARD>3.0.0</METADATA_STANDARD></DATASET>"], BigpictureVersion.V3_0),
        (
            [
                "<IMAGE_SET/>",
                "<DATASET_SET><DATASET><METADATA_STANDARD>3.0.0</METADATA_STANDARD></DATASET></DATASET_SET>",
                "<SAMPLE_SET/>",
            ],
            BigpictureVersion.V3_0,
        ),
    ],
)
def test_get_bp_version_from_documents(xml_docs, expected_version):
    assert get_bp_version_from_documents(xml_docs) == expected_version


@pytest.mark.parametrize(
    ("xml_docs", "expected_error"),
    [
        (["<DATASET_SET><DATASET/></DATASET_SET>"], "Missing"),
        (["<IMAGE_SET/>"], "Expecting exactly one 'dataset' metadata object but found 0."),
        (
            ["<DATASET_SET><DATASET><METADATA_STANDARD>4.0.0</METADATA_STANDARD></DATASET></DATASET_SET>"],
            "Unsupported .* 4.0.0",
        ),
        (
            ["<DATASET_SET><DATASET><METADATA_STANDARD>2.1.0</METADATA_STANDARD></DATASET></DATASET_SET>"],
            "Unsupported .* 2.1.0",
        ),
        (
            ["<DATASET_SET><DATASET><METADATA_STANDARD>3.0</METADATA_STANDARD></DATASET></DATASET_SET>"],
            r"Unsupported .* 3.0\.",
        ),
        (
            [
                "<DATASET_SET><DATASET><METADATA_STANDARD>2.0.0</METADATA_STANDARD></DATASET></DATASET_SET>",
                "<DATASET_SET><DATASET><METADATA_STANDARD>3.0.0</METADATA_STANDARD></DATASET></DATASET_SET>",
            ],
            "Conflicting Bigpicture metadata versions: 2.0, 3.0.",
        ),
    ],
    ids=["no-element", "no-dataset", "unknown-major", "unknown-minor", "no-patch", "conflicting"],
)
def test_get_bp_version_from_documents_error(xml_docs, expected_error):
    with pytest.raises(UserException, match=expected_error):
        get_bp_version_from_documents(xml_docs)


@pytest.mark.parametrize(
    ("xml", "expected"),
    [
        ("<DATASET><METADATA_STANDARD>2.0.0</METADATA_STANDARD></DATASET>", BigpictureVersion.V2_0),
        (
            "<DATASET_SET><DATASET><METADATA_STANDARD>3.0.1</METADATA_STANDARD></DATASET></DATASET_SET>",
            BigpictureVersion.V3_0,
        ),
        ("<DATASET/>", "Missing"),
        ("<DATASET><METADATA_STANDARD>4.0.0</METADATA_STANDARD></DATASET>", "Unsupported .* 4.0.0"),
        (
            "<DATASET_SET><DATASET><METADATA_STANDARD>2.0.0</METADATA_STANDARD></DATASET>"
            "<DATASET><METADATA_STANDARD>3.0.0</METADATA_STANDARD></DATASET></DATASET_SET>",
            "Conflicting Bigpicture metadata standard versions: 2.0.0, 3.0.0.",
        ),
    ],
    ids=["dataset", "dataset-set", "no-element", "unsupported", "conflicting"],
)
def test_get_bp_version_from_dataset(xml, expected):
    dataset = XmlProcessor.parse_xml(xml).getroot()
    if isinstance(expected, BigpictureVersion):
        assert get_bp_version_from_dataset(dataset) == expected
    else:
        with pytest.raises(UserException, match=expected):
            get_bp_version_from_dataset(dataset)


def test_prepare_files_3():
    """The image, annotation, ontology and annotation task files of a 3.0 submission."""

    service = _bp_submission_service()
    service._processor, _, _ = BigpictureObjectSubmissionService._create_processor(_bp_objects(SUBMISSION_3_DIR))

    assert sorted(f.path for f in service.prepare_files("1")) == [
        f"DATASET_1/{BP_ANNOTATION_1_FILE}.c4gh",
        f"DATASET_1/{BP_ANNOTATION_2_FILE}.c4gh",
        f"DATASET_1/{BP_ANNOTATION_TASK_FILE}.c4gh",
        f"DATASET_1/{BP_IMAGE_1_FILE}.c4gh",
        f"DATASET_1/{BP_IMAGE_2_FILE}.c4gh",
        f"DATASET_1/{BP_ONTOLOGY_FILE}.c4gh",
    ]


@pytest.mark.parametrize(
    ("replacements", "error"),
    [
        (
            {"ontology": (BP_ONTOLOGY_FILE, "ANNOTATIONS/ontology.json")},
            "ONTOLOGY file 'ANNOTATIONS/ontology.json.c4gh' must be in directory 'ONTOLOGIES'.",
        ),
        (
            {"annotation_task": (BP_ANNOTATION_TASK_FILE, "ANNOTATIONS/task.pdf")},
            "ANNOTATION_TASK file 'ANNOTATIONS/task.pdf.c4gh' must be in directory 'ANNOTATION_TASKS'.",
        ),
        (
            {"annotation": (BP_ANNOTATION_2_FILE, BP_ANNOTATION_1_FILE)},
            f"ANNOTATION file '{BP_ANNOTATION_1_FILE}.c4gh' is already declared by ANNOTATION.",
        ),
    ],
)
def test_prepare_files_3_error(replacements, error):
    service = _bp_submission_service()
    service._processor, _, _ = BigpictureObjectSubmissionService._create_processor(
        _bp_objects(SUBMISSION_3_DIR, **replacements)
    )

    with pytest.raises(UserException, match=re.escape(error)):
        service.prepare_files("1")
