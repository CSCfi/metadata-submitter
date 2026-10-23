import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from metadata_backend.api.exceptions import SystemException, UserException
from metadata_backend.api.models.models import File, Registration
from metadata_backend.api.models.sda import FileItem
from metadata_backend.api.models.submission import Rems, Submission, SubmissionWorkflow
from metadata_backend.api.processors.xml.bigpicture import BP_XML_OBJECT_CONFIGS, BigpictureVersion
from metadata_backend.api.processors.xml.datacite import DATACITE_OBJECT_TYPE, DATACITE_SCHEMA
from metadata_backend.api.processors.xml.fega import FEGA_XML_OBJECT_CONFIG
from metadata_backend.api.services.crypt import Crypt4GHPublicKeyProvider
from metadata_backend.api.services.file import S3InboxSDAService
from metadata_backend.api.services.workflow import XmlSubmissionWorkflowProfile, workflow_profile

SD = workflow_profile(SubmissionWorkflow.SD)
FEGA = workflow_profile(SubmissionWorkflow.FEGA)
BP = workflow_profile(SubmissionWorkflow.BP)

SUBMISSION_ID = "submission-id"
SUBMISSION_NAME = "submission-name"
SUBMISSION_TITLE = "submission-title"
REMS_ORGANIZATION_ID = "rems-organization-id"
DOI = "10.1234/doi"
METAX_ID = "metax-id"


def workflow_submission(workflow: SubmissionWorkflow, metadata_version: str | None = None) -> Submission:
    """Get a submission of the workflow, which is not stored."""
    return Submission(
        projectId="project-id",
        submissionId=SUBMISSION_ID,
        name=SUBMISSION_NAME,
        title=SUBMISSION_TITLE,
        description="submission-description",
        workflow=workflow,
        metadataVersion=metadata_version,
    )


def _registration(doi: str | None = None, metax_id: str | None = None) -> Registration:
    return Registration(
        submissionId=SUBMISSION_ID,
        title=SUBMISSION_TITLE,
        description="submission-description",
        doi=doi,
        metaxId=metax_id,
    )


@pytest.mark.parametrize("workflow", list(SubmissionWorkflow))
def test_every_workflow_has_profile(workflow):
    assert workflow_profile(workflow).workflow == workflow


def test_only_sd_requires_datacite():
    assert [w for w in SubmissionWorkflow if workflow_profile(w).requires_datacite] == [SubmissionWorkflow.SD]


def test_sd_has_no_xml_metadata():
    assert not isinstance(SD, XmlSubmissionWorkflowProfile)


# XML configuration.


def test_xml_config_fega():
    assert FEGA.xml_config(workflow_submission(SubmissionWorkflow.FEGA)) is FEGA_XML_OBJECT_CONFIG


@pytest.mark.parametrize("version", list(BigpictureVersion))
def test_xml_config_bp(version):
    assert BP.xml_config(workflow_submission(SubmissionWorkflow.BP, version.value)) is BP_XML_OBJECT_CONFIGS[version]


def test_xml_config_bp_without_metadata_version():
    with pytest.raises(SystemException, match="has no metadata version"):
        BP.xml_config(workflow_submission(SubmissionWorkflow.BP))


# Object types.


def _xml_schema_type_cases():
    """Every schema type of every XML workflow and metadata version, with its object types."""
    configs = [(SubmissionWorkflow.FEGA, None, FEGA_XML_OBJECT_CONFIG)] + [
        (SubmissionWorkflow.BP, version.value, BP_XML_OBJECT_CONFIGS[version]) for version in BigpictureVersion
    ]
    cases = []
    for workflow, metadata_version, config in configs:
        for schema_type in dict.fromkeys(p.schema_type for p in config.object_paths):
            object_types = [p.object_type for p in config.object_paths if p.schema_type == schema_type]
            cases.append(
                pytest.param(
                    workflow,
                    metadata_version,
                    schema_type,
                    object_types,
                    id=f"{workflow.value}-{metadata_version or 'unversioned'}-{schema_type}",
                )
            )
    return cases


@pytest.mark.parametrize("workflow", list(SubmissionWorkflow))
def test_object_types_without_filter(workflow):
    # All the submission's objects are listed.
    submission = workflow_submission(
        workflow, BigpictureVersion.V3_0.value if workflow == SubmissionWorkflow.BP else None
    )
    assert workflow_profile(workflow).object_types(submission) is None


@pytest.mark.parametrize(
    ("workflow", "metadata_version", "schema_type", "expected_object_types"), _xml_schema_type_cases()
)
def test_object_types_by_schema_type(workflow, metadata_version, schema_type, expected_object_types):
    # The schema type is resolved by the workflow and its metadata version.
    submission = workflow_submission(workflow, metadata_version)
    assert workflow_profile(workflow).object_types(submission, schema_type=schema_type) == expected_object_types


@pytest.mark.parametrize(
    ("workflow", "metadata_version", "schema_type", "expected_object_types"), _xml_schema_type_cases()
)
def test_object_types_by_object_type(workflow, metadata_version, schema_type, expected_object_types):
    submission = workflow_submission(workflow, metadata_version)
    for object_type in expected_object_types:
        assert workflow_profile(workflow).object_types(submission, object_type=object_type) == [object_type]


def test_object_types_datacite():
    # Bigpicture submissions have DataCite metadata objects.
    for version in BigpictureVersion:
        bp = workflow_submission(SubmissionWorkflow.BP, version.value)
        assert BP.object_types(bp, object_type=DATACITE_OBJECT_TYPE) == [DATACITE_OBJECT_TYPE]
        assert BP.object_types(bp, schema_type=DATACITE_SCHEMA) == [DATACITE_OBJECT_TYPE]

    # Submissions of other workflows do not.
    for workflow in SubmissionWorkflow:
        if workflow == SubmissionWorkflow.BP:
            continue
        profile = workflow_profile(workflow)
        submission = workflow_submission(workflow)
        with pytest.raises(UserException, match=f"Unknown object type: {DATACITE_OBJECT_TYPE}"):
            profile.object_types(submission, object_type=DATACITE_OBJECT_TYPE)
        with pytest.raises(UserException, match=f"Unknown schema type: {DATACITE_SCHEMA}"):
            profile.object_types(submission, schema_type=DATACITE_SCHEMA)


def test_object_types_bp_added_in_v3_unknown_in_v2():
    v2 = BP_XML_OBJECT_CONFIGS[BigpictureVersion.V2_0]
    v3 = BP_XML_OBJECT_CONFIGS[BigpictureVersion.V3_0]
    submission = workflow_submission(SubmissionWorkflow.BP, BigpictureVersion.V2_0.value)

    added_schema_types = {p.schema_type for p in v3.object_paths} - {p.schema_type for p in v2.object_paths}
    assert added_schema_types
    for schema_type in added_schema_types:
        with pytest.raises(UserException, match=f"Unknown schema type: {schema_type}"):
            BP.object_types(submission, schema_type=schema_type)

    added_object_types = {p.object_type for p in v3.object_paths} - {p.object_type for p in v2.object_paths}
    assert added_object_types
    for object_type in added_object_types:
        with pytest.raises(UserException, match=f"Unknown object type: {object_type}"):
            BP.object_types(submission, object_type=object_type)


@pytest.mark.parametrize("workflow", [SubmissionWorkflow.FEGA, SubmissionWorkflow.BP])
def test_object_types_xml_unknown(workflow):
    submission = workflow_submission(
        workflow, BigpictureVersion.V3_0.value if workflow == SubmissionWorkflow.BP else None
    )
    with pytest.raises(UserException, match="Unknown object type: unknown"):
        workflow_profile(workflow).object_types(submission, object_type="unknown")
    with pytest.raises(UserException, match="Unknown schema type: unknown"):
        workflow_profile(workflow).object_types(submission, schema_type="unknown")


def test_object_types_sd():
    # SD submissions have no metadata objects.
    submission = workflow_submission(SubmissionWorkflow.SD)
    with pytest.raises(UserException, match="Unknown object type: study"):
        SD.object_types(submission, object_type="study")
    with pytest.raises(UserException, match="Unknown schema type: study"):
        SD.object_types(submission, schema_type="study")


# Registration and discovery.


def test_registration_title_sd_is_submission_title():
    rems = Rems(workflowId=1, organizationId=REMS_ORGANIZATION_ID)
    assert SD.registration_title(workflow_submission(SubmissionWorkflow.SD), rems) == SUBMISSION_TITLE


def test_registration_title_bp_is_rems_catalogue_item_title():
    rems = Rems(workflowId=1, organizationId=REMS_ORGANIZATION_ID)
    assert BP.registration_title(workflow_submission(SubmissionWorkflow.BP), rems) == (
        f"{SUBMISSION_NAME} ({REMS_ORGANIZATION_ID}, {SUBMISSION_ID})"
    )


@pytest.mark.parametrize(
    ("registration", "expected_discovery_id"),
    [
        pytest.param(_registration(doi=DOI, metax_id=METAX_ID), METAX_ID, id="metax_id_first"),
        pytest.param(_registration(doi=DOI), DOI, id="doi_without_metax_id"),
        pytest.param(_registration(), SUBMISSION_ID, id="submission_id_without_doi"),
    ],
)
def test_discovery_id_sd(registration, expected_discovery_id):
    assert SD.discovery_id(workflow_submission(SubmissionWorkflow.SD), registration) == expected_discovery_id


def test_discovery_id_bp():
    registration = _registration(doi=DOI, metax_id=METAX_ID)
    assert BP.discovery_id(workflow_submission(SubmissionWorkflow.BP), registration) == SUBMISSION_ID


@pytest.mark.parametrize(
    ("registration", "expected_rems_resource_id"),
    [
        pytest.param(_registration(doi=DOI), DOI, id="doi_first"),
        pytest.param(_registration(), SUBMISSION_ID, id="submission_id_without_doi"),
    ],
)
def test_rems_resource_id_sd(registration, expected_rems_resource_id):
    assert SD.rems_resource_id(workflow_submission(SubmissionWorkflow.SD), registration) == expected_rems_resource_id


def test_rems_resource_id_bp():
    assert BP.rems_resource_id(workflow_submission(SubmissionWorkflow.BP), _registration(doi=DOI)) == SUBMISSION_ID


FEGA_UNSUPPORTED = "Unsupported workflow: FEGA"


def test_fega_cannot_create_submission():
    with pytest.raises(UserException, match=FEGA_UNSUPPORTED):
        FEGA.object_submission_service(services=None)


async def test_fega_cannot_prepare_publish():
    with pytest.raises(UserException, match=FEGA_UNSUPPORTED):
        await FEGA.prepare_publish(services=None, submission_id=SUBMISSION_ID, user_id="user-id", jwt=None)


def test_fega_cannot_register():
    submission = workflow_submission(SubmissionWorkflow.FEGA)
    registration = _registration()

    with pytest.raises(UserException, match=FEGA_UNSUPPORTED):
        FEGA.registration_title(submission, Rems(workflowId=1))
    with pytest.raises(UserException, match=FEGA_UNSUPPORTED):
        FEGA.discovery_id(submission, registration)
    with pytest.raises(UserException, match=FEGA_UNSUPPORTED):
        FEGA.rems_resource_id(submission, registration)


@pytest.mark.parametrize("xml_in_inbox", [True, False])
async def test_bp_check_files_for_publish(xml_in_inbox):
    """Test that Bigpicture check files for publish succeeds with and without metadata XMLw already in the SDA inbox.

    A publish that fails after uploading may leave metadata XMLs in the SDA inbox.
    """
    data_file_path = f"DATASET_{SUBMISSION_ID}/IMAGES/IMAGE_1/img1.dcm.c4gh"
    dataset_xml_path = f"DATASET_{SUBMISSION_ID}/METADATA/dataset.xml.c4gh"
    inbox_paths = [data_file_path, dataset_xml_path] if xml_in_inbox else [data_file_path]

    # The SDA Admin API lists the files in the inbox.
    admin_handler = AsyncMock()
    admin_handler.get_user_files.return_value = [
        FileItem(fileID=str(uuid.uuid4()), inboxPath=path, fileStatus="uploaded", createdAt="2026-01-01T00:00:00Z")
        for path in inbox_paths
    ]

    async def get_files(**_kwargs):
        yield File(submissionId=SUBMISSION_ID, path=data_file_path)

    services = SimpleNamespace(
        file_provider=S3InboxSDAService(admin_handler, AsyncMock(spec=Crypt4GHPublicKeyProvider)),
        file=SimpleNamespace(get_files=get_files, is_file_by_path=AsyncMock(return_value=True)),
    )

    # Raises if a file is missing from the inbox, or the inbox has an unexpected file.
    await BP._check_files_for_publish(services, "user-id", SUBMISSION_ID, [dataset_xml_path])
