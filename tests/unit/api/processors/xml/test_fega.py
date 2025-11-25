import uuid

from metadata_backend.api.processors.models import ObjectIdentifier
from metadata_backend.api.processors.xml.fega import (
    FEGA_ANALYSIS_PATH,
    FEGA_ANALYSIS_SCHEMA,
    FEGA_ANALYSIS_SCHEMA_AND_PATH,
    FEGA_DAC_PATH,
    FEGA_DAC_SCHEMA,
    FEGA_DAC_SCHEMA_AND_PATH,
    FEGA_DATASET_PATH,
    FEGA_DATASET_SCHEMA,
    FEGA_DATASET_SCHEMA_AND_PATH,
    FEGA_EXPERIMENT_PATH,
    FEGA_EXPERIMENT_SCHEMA,
    FEGA_EXPERIMENT_SCHEMA_AND_PATH,
    FEGA_FULL_SUBMISSION_XML_OBJECT_CONFIG,
    FEGA_POLICY_PATH,
    FEGA_POLICY_SCHEMA,
    FEGA_POLICY_SCHEMA_AND_PATH,
    FEGA_RUN_PATH,
    FEGA_RUN_SCHEMA,
    FEGA_RUN_SCHEMA_AND_PATH,
    FEGA_SAMPLE_PATH,
    FEGA_SAMPLE_SCHEMA,
    FEGA_SAMPLE_SCHEMA_AND_PATH,
    FEGA_STUDY_PATH,
    FEGA_STUDY_SCHEMA,
    FEGA_STUDY_SCHEMA_AND_PATH,
    FEGA_SUBMISSION_PATH,
    FEGA_SUBMISSION_SCHEMA,
    FEGA_SUBMISSION_SCHEMA_AND_PATH,
    _get_xml_object_type_fega,
)
from metadata_backend.api.processors.xml.processors import XmlFileDocumentsProcessor

from .test_utils import TEST_FILES_DIR, assert_object, assert_ref, assert_ref_length

SUBMISSION_DIR = TEST_FILES_DIR / "xml" / "fega"


def create_xml_object_identifier_fega(schema_type: str, root_path: str, name: str, id: str):
    return ObjectIdentifier(
        schema_type=schema_type, object_type=_get_xml_object_type_fega(root_path), root_path=root_path, name=name, id=id
    )


async def test_fega_submission():
    """Test self-contained FEGA submission with alias references."""

    processor = XmlFileDocumentsProcessor(
        FEGA_FULL_SUBMISSION_XML_OBJECT_CONFIG,
        str(SUBMISSION_DIR),
        [
            "analysis.xml",
            "dac.xml",
            "dataset.xml",
            "experiment.xml",
            "policy.xml",
            "run.xml",
            "sample.xml",
            "study.xml",
            "submission.xml",
        ],
    )

    analysis_name = "1"
    dac_name = "1"
    dataset_name = "1"
    experiment_name = "1"
    policy_name = "1"
    run_name = "1"
    sample_name = "1"
    study_name = "1"
    submission_name = "1"

    # Assert not accessioned state
    #

    # Analysis
    assert_object(processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, None, title="test_title")
    assert_ref_length(processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, 4)
    assert_ref(processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, FEGA_STUDY_SCHEMA_AND_PATH, study_name, None)
    assert_ref(processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, FEGA_SAMPLE_SCHEMA_AND_PATH, sample_name, None)
    assert_ref(
        processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, None
    )
    assert_ref(processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, FEGA_RUN_SCHEMA_AND_PATH, run_name, None)
    # Dac
    assert_object(processor, FEGA_DAC_SCHEMA_AND_PATH, dac_name, None, title="test_title")
    assert_ref_length(processor, FEGA_DAC_SCHEMA_AND_PATH, dac_name, 0)
    # Dataset
    assert_object(
        processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, None, title="test_title", description="test_description"
    )
    assert_ref_length(processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, 3)
    assert_ref(processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, FEGA_RUN_SCHEMA_AND_PATH, run_name, None)
    assert_ref(
        processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, None
    )
    assert_ref(processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, FEGA_POLICY_SCHEMA_AND_PATH, policy_name, None)
    # Experiment
    assert_object(processor, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, None, title="test_title")
    assert_ref_length(processor, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, 2)
    assert_ref(
        processor, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, FEGA_STUDY_SCHEMA_AND_PATH, study_name, None
    )
    assert_ref(
        processor, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, FEGA_SAMPLE_SCHEMA_AND_PATH, sample_name, None
    )
    # Policy
    assert_object(processor, FEGA_POLICY_SCHEMA_AND_PATH, policy_name, None, title="test_title")
    assert_ref_length(processor, FEGA_POLICY_SCHEMA_AND_PATH, policy_name, 1)
    assert_ref(processor, FEGA_POLICY_SCHEMA_AND_PATH, policy_name, FEGA_DAC_SCHEMA_AND_PATH, dac_name, None)
    # Run
    assert_object(processor, FEGA_RUN_SCHEMA_AND_PATH, run_name, None, title="test_title")
    assert_ref_length(processor, FEGA_RUN_SCHEMA_AND_PATH, run_name, 1)
    assert_ref(processor, FEGA_RUN_SCHEMA_AND_PATH, run_name, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, None)
    # Sample
    assert_object(
        processor, FEGA_SAMPLE_SCHEMA_AND_PATH, sample_name, None, title="test_title", description="test_description"
    )
    assert_ref_length(processor, FEGA_SAMPLE_SCHEMA_AND_PATH, sample_name, 0)
    # Study
    assert_object(
        processor, FEGA_STUDY_SCHEMA_AND_PATH, study_name, None, title="test_title", description="test_description"
    )
    assert_ref_length(processor, FEGA_STUDY_SCHEMA_AND_PATH, study_name, 0)
    # Submission
    assert_object(processor, FEGA_SUBMISSION_SCHEMA_AND_PATH, submission_name, None)
    assert_ref_length(processor, FEGA_SUBMISSION_SCHEMA_AND_PATH, submission_name, 0)

    # Assign accessions
    #

    # Analysis
    analysis_id = f"analysis_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_fega(FEGA_ANALYSIS_SCHEMA, FEGA_ANALYSIS_PATH, analysis_name, analysis_id)
    )
    # Dac
    dac_id = f"dac_{str(uuid.uuid4())}"
    processor.set_object_id(create_xml_object_identifier_fega(FEGA_DAC_SCHEMA, FEGA_DAC_PATH, dac_name, dac_id))
    # Dataset
    dataset_id = f"dataset_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_fega(FEGA_DATASET_SCHEMA, FEGA_DATASET_PATH, dataset_name, dataset_id)
    )
    # Experiment
    experiment_id = f"experiment_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_fega(FEGA_EXPERIMENT_SCHEMA, FEGA_EXPERIMENT_PATH, experiment_name, experiment_id)
    )
    # Policy
    policy_id = f"policy_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_fega(FEGA_POLICY_SCHEMA, FEGA_POLICY_PATH, policy_name, policy_id)
    )
    # Run
    run_id = f"run_{str(uuid.uuid4())}"
    processor.set_object_id(create_xml_object_identifier_fega(FEGA_RUN_SCHEMA, FEGA_RUN_PATH, run_name, run_id))
    # Sample
    sample_id = f"sample_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_fega(FEGA_SAMPLE_SCHEMA, FEGA_SAMPLE_PATH, sample_name, sample_id)
    )
    # Study
    study_id = f"study_{str(uuid.uuid4())}"
    processor.set_object_id(create_xml_object_identifier_fega(FEGA_STUDY_SCHEMA, FEGA_STUDY_PATH, study_name, study_id))
    # Submission
    submission_id = f"submission_{str(uuid.uuid4())}"
    processor.set_object_id(
        create_xml_object_identifier_fega(FEGA_SUBMISSION_SCHEMA, FEGA_SUBMISSION_PATH, submission_name, submission_id)
    )

    # Assert accessioned state
    #

    # Analysis
    assert_object(processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, analysis_id)
    assert_ref_length(processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, 4)
    assert_ref(
        processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, FEGA_STUDY_SCHEMA_AND_PATH, study_name, study_id
    )
    assert_ref(
        processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, FEGA_SAMPLE_SCHEMA_AND_PATH, sample_name, sample_id
    )
    assert_ref(
        processor,
        FEGA_ANALYSIS_SCHEMA_AND_PATH,
        analysis_name,
        FEGA_EXPERIMENT_SCHEMA_AND_PATH,
        experiment_name,
        experiment_id,
    )
    assert_ref(processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, FEGA_RUN_SCHEMA_AND_PATH, run_name, run_id)
    # Dac
    assert_object(processor, FEGA_DAC_SCHEMA_AND_PATH, dac_name, dac_id)
    assert_ref_length(processor, FEGA_DAC_SCHEMA_AND_PATH, dac_name, 0)
    # Dataset
    assert_object(processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, dataset_id)
    assert_ref_length(processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, 3)
    assert_ref(processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, FEGA_RUN_SCHEMA_AND_PATH, run_name, run_id)
    assert_ref(
        processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, analysis_id
    )
    assert_ref(
        processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, FEGA_POLICY_SCHEMA_AND_PATH, policy_name, policy_id
    )
    # Experiment
    assert_object(processor, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, experiment_id)
    assert_ref_length(processor, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, 2)
    assert_ref(
        processor, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, FEGA_STUDY_SCHEMA_AND_PATH, study_name, study_id
    )
    assert_ref(
        processor, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, FEGA_SAMPLE_SCHEMA_AND_PATH, sample_name, sample_id
    )
    # Policy
    assert_object(processor, FEGA_POLICY_SCHEMA_AND_PATH, policy_name, policy_id)
    assert_ref_length(processor, FEGA_POLICY_SCHEMA_AND_PATH, policy_name, 1)
    assert_ref(processor, FEGA_POLICY_SCHEMA_AND_PATH, policy_name, FEGA_DAC_SCHEMA_AND_PATH, dac_name, dac_id)
    # Run
    assert_object(processor, FEGA_RUN_SCHEMA_AND_PATH, run_name, run_id)
    assert_ref_length(processor, FEGA_RUN_SCHEMA_AND_PATH, run_name, 1)
    assert_ref(
        processor, FEGA_RUN_SCHEMA_AND_PATH, run_name, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, experiment_id
    )
    # Sample
    assert_object(processor, FEGA_SAMPLE_SCHEMA_AND_PATH, sample_name, sample_id)
    assert_ref_length(processor, FEGA_SAMPLE_SCHEMA_AND_PATH, sample_name, 0)
    # Study
    assert_object(processor, FEGA_STUDY_SCHEMA_AND_PATH, study_name, study_id)
    assert_ref_length(processor, FEGA_STUDY_SCHEMA_AND_PATH, study_name, 0)
    # Submission
    assert_object(processor, FEGA_SUBMISSION_SCHEMA_AND_PATH, submission_name, submission_id)
    assert_ref_length(processor, FEGA_SUBMISSION_SCHEMA_AND_PATH, submission_name, 0)
