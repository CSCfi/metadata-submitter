"""Tests for publish API handler."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from metadata_backend.api.exceptions import SystemException
from metadata_backend.api.handlers.publish import PublishAPIHandler
from metadata_backend.api.json import to_json_dict
from metadata_backend.api.models.datacite import Subject
from metadata_backend.api.models.models import Registration
from metadata_backend.api.models.submission import Rems, Submission, SubmissionMetadata, SubmissionWorkflow
from metadata_backend.api.processors.xml.bigpicture import BP_SAMPLE_OBJECT_TYPES
from metadata_backend.api.services.file import FileProviderService, S3InboxSDAService
from metadata_backend.conf.conf import API_PREFIX
from metadata_backend.database.postgres.models import FileEntity
from metadata_backend.database.postgres.repositories.submission import (
    SUB_FIELD_METADATA,
    SUB_FIELD_REMS,
)
from metadata_backend.services.rems_service import RemsServiceHandler
from tests.unit.database.postgres.helpers import create_object_entity, create_submission_entity
from tests.unit.patches.user import patch_verify_authorization, patch_verify_user_project

from ...conftest import TEST_DISCOVERY_URL
from ...patches.datacite_service import (
    patch_datacite_create_draft_doi,
    patch_datacite_publish,
)
from ...patches.metax_service import (
    patch_metax_create_draft_dataset,
    patch_metax_publish_dataset,
    patch_metax_update_dataset_description,
    patch_metax_update_dataset_metadata,
)
from ...patches.pid_service import (
    patch_pid_create_draft_doi,
    patch_pid_publish,
)
from ...patches.rems_service import (
    MOCK_REMS_DEFAULT_LICENSE_ID,
    MOCK_REMS_DEFAULT_ORGANISATION_ID,
    MOCK_REMS_DEFAULT_WORKFLOW_ID,
    mock_rems_catalogue_id,
    mock_rems_resource_id,
    patch_rems_create_catalogue_item,
    patch_rems_create_resource,
)
from .common import SUBMISSION_METADATA


async def test_publish_submission_sd(csc_client, submission_repository, object_repository, file_repository):
    """Test publishing of CSC submission."""

    # REMS information.
    rems = Rems(
        organizationId=MOCK_REMS_DEFAULT_ORGANISATION_ID,
        workflowId=MOCK_REMS_DEFAULT_WORKFLOW_ID,
        licenses=[MOCK_REMS_DEFAULT_LICENSE_ID],
    )

    submission_title = f"title_{str(uuid.uuid4())}"
    submission_description = f"description_{str(uuid.uuid4())}"

    # The submission contains one file.
    file_path = f"path_{str(uuid.uuid4())}"
    file_bytes = 1024

    # Mock data.
    metax_id = f"metax_{str(uuid.uuid4())}"
    doi_part1 = f"doi_{str(uuid.uuid4())}"
    doi_part2 = f"doi_{str(uuid.uuid4())}"
    doi = f"{doi_part1}/{doi_part2}"

    # Test publishing fails when submission has no bucket.
    with patch_verify_user_project, patch_verify_authorization:
        # Create submission without bucket.
        submission_entity = create_submission_entity()
        submission_id = await submission_repository.add_submission(submission_entity)
        response = csc_client.patch(f"{API_PREFIX}/publish/{submission_id}")
        data = response.json()
        assert response.status_code == 400
        assert data["detail"] == f"Submission '{submission_id}' is not linked to any bucket."

    file_provider_cls = "metadata_backend.api.services.file.FileProviderService"

    with (
        patch_verify_user_project,
        patch_verify_authorization,
        patch(
            "metadata_backend.api.handlers.publish.PublishAPIHandler._upload_bp_metadata_xmls",
            new_callable=AsyncMock,
        ) as mock_upload_bp_metadata,
        # File provider
        patch(f"{file_provider_cls}.list_files_in_bucket", new_callable=AsyncMock) as mock_file_provider,
        patch_pid_create_draft_doi(doi) as mock_pid_create_draft_doi,
        patch_pid_publish() as mock_pid_publish,
        # Metax
        patch_metax_create_draft_dataset(metax_id) as mock_metax_create_draft_dataset,
        patch_metax_update_dataset_metadata() as mock_metax_update_dataset_metadata,
        patch_metax_update_dataset_description() as mock_metax_update_dataset_description,
        patch_metax_publish_dataset() as mock_metax_publish_dataset,
        # Rems
        patch_rems_create_resource() as mock_rems_create_resource,
        patch_rems_create_catalogue_item() as mock_rems_create_catalogue_item,
    ):
        # Mock file provider.
        # Create submission and files to allow the submission to be published.
        submission_entity = create_submission_entity(
            title=submission_title,
            description=submission_description,
            document={SUB_FIELD_METADATA: SUBMISSION_METADATA, SUB_FIELD_REMS: to_json_dict(rems)},
            bucket="test-bucket",
        )

        # Test edge case where file service has not received any files.
        submission_id = await submission_repository.add_submission(submission_entity)
        mock_file_provider.return_value = FileProviderService.Files(root=[])
        response = csc_client.patch(f"{API_PREFIX}/publish/{submission_id}")
        data = response.json()
        assert response.status_code == 400
        assert data["detail"] == f"Submission '{submission_id}' does not have any data files."

        # Mock file provider
        mock_file_provider.return_value = FileProviderService.Files(
            [FileProviderService.File(path=file_path, bytes=file_bytes)]
        )

        # Publish submission.
        response = csc_client.patch(f"{API_PREFIX}/publish/{submission_id}")
        data = response.json()
        assert response.status_code == 200
        assert data == {"submissionId": submission_id}

        mock_pid_create_draft_doi.assert_awaited_once()
        mock_pid_publish.assert_awaited_once()

        # Assert Metax.
        mock_metax_create_draft_dataset.assert_awaited_once_with(doi, submission_title, submission_description)

        expected_submission_metadata = SubmissionMetadata.model_validate(SUBMISSION_METADATA)
        expected_submission_metadata.subjects = [
            Subject(
                **s,
                subjectScheme="Korkeakoulujen tutkimustiedonkeruussa käytettävä tieteenalaluokitus",
                schemeUri="http://www.yso.fi/onto/okm-tieteenala/conceptscheme",
                valueUri=f"http://www.yso.fi/onto/okm-tieteenala/ta{s['subject'].split(' - ')[0]}",
                classificationCode=s["subject"].split(" - ")[0],
            )
            for s in SUBMISSION_METADATA.get("subjects", [])
        ]

        mock_metax_update_dataset_metadata.assert_awaited_once()
        mock_metax_update_dataset_description.assert_awaited_once_with(
            metax_id,
            f"{submission_description}\n\nSD Apply Application link: "
            f"{RemsServiceHandler.get_application_url(str(mock_rems_catalogue_id))}",
        )

        mock_metax_publish_dataset.assert_awaited_once_with(metax_id, doi)

        # Assert Rems.
        mock_rems_create_resource.assert_awaited_once_with(rems.organizationId, rems.licenses, doi)
        mock_rems_create_catalogue_item.assert_awaited_once_with(
            rems.organizationId,
            rems.workflowId,
            mock_rems_resource_id,
            submission_title,
            TEST_DISCOVERY_URL.format(id=metax_id),
        )

        # BP metadata upload should never run for SD workflow.
        mock_upload_bp_metadata.assert_not_awaited()


async def test_publish_submission_bp(nbis_client, submission_repository, object_repository, file_repository):
    """Test publishing of BP submission."""

    # REMS information.
    rems = Rems(
        organizationId=MOCK_REMS_DEFAULT_ORGANISATION_ID,
        workflowId=MOCK_REMS_DEFAULT_WORKFLOW_ID,
        licenses=[MOCK_REMS_DEFAULT_LICENSE_ID],
    )

    # The submission contains one dataset metadata object.
    dataset_object_type = "dataset"
    dataset_title = f"title_{str(uuid.uuid4())}"
    dataset_description = f"description_{str(uuid.uuid4())}"

    # The submission contains one file.
    file_path = f"path_{str(uuid.uuid4())}"
    file_bytes = 1024

    # Mock data.
    doi_part1 = f"doi_{str(uuid.uuid4())}"
    doi_part2 = f"doi_{str(uuid.uuid4())}"
    doi = f"{doi_part1}/{doi_part2}"

    # Create submission and files to allow the submission to be published.

    # Create submission.
    workflow = SubmissionWorkflow.BP
    submission_entity = create_submission_entity(
        workflow=workflow,
        document={SUB_FIELD_METADATA: SUBMISSION_METADATA, SUB_FIELD_REMS: to_json_dict(rems)},
        bucket="test-bucket",
        title=dataset_title,
    )
    submission_id = await submission_repository.add_submission(submission_entity)

    # Create metadata object.
    object_entity = create_object_entity(
        project_id=submission_entity.project_id,
        submission_id=submission_id,
        object_type=dataset_object_type,
        document={},
        title=dataset_title,
        description=dataset_description,
    )
    await object_repository.add_object(object_entity, workflow)

    # Create file.
    file_entity = FileEntity(
        submission_id=submission_id,
        object_id=object_entity.object_id,
        path=file_path,
        bytes=file_bytes,
    )
    await file_repository.add_file(file_entity, workflow)

    # Publish submission.
    #

    with (
        patch_verify_user_project,
        patch_verify_authorization,
        patch(
            "metadata_backend.api.handlers.publish.PublishAPIHandler._upload_bp_metadata_xmls",
            new_callable=AsyncMock,
        ) as mock_upload_bp_metadata,
        patch(
            "metadata_backend.api.services.file.S3InboxSDAService.check_files_exist", new_callable=AsyncMock
        ) as mock_check_files_exist,
        patch_datacite_create_draft_doi(doi) as mock_datacite_create_draft_doi,
        patch_datacite_publish() as mock_datacite_publish,
        patch_pid_create_draft_doi(doi) as mock_pid_create_draft_doi,
        patch_pid_publish() as mock_pid_publish,
        # Rems
        patch_rems_create_resource() as mock_rems_create_resource,
        patch_rems_create_catalogue_item() as mock_rems_create_catalogue_item,
    ):
        mock_check_files_exist.return_value = []

        # Publish submission.
        response = nbis_client.patch(
            f"{API_PREFIX}/publish/{submission_id}", headers={"Authorization": "Bearer oidc-token"}
        )
        data = response.json()
        assert response.status_code == 200
        assert data == {"submissionId": submission_id}

        mock_datacite_create_draft_doi.assert_awaited_once()
        mock_datacite_publish.assert_awaited_once()
        mock_pid_create_draft_doi.assert_not_awaited()
        mock_pid_publish.assert_not_awaited()

        # Assert Beacon.
        # TODO(improve): BP beacon service not implement

        # Assert Rems.
        mock_rems_create_resource.assert_awaited_once_with(rems.organizationId, rems.licenses, submission_id)
        mock_rems_create_catalogue_item.assert_awaited_once_with(
            rems.organizationId,
            rems.workflowId,
            1,  # REMS resource id
            f"{submission_entity.name} ({rems.organizationId}, {submission_id})",
            TEST_DISCOVERY_URL.format(id=submission_id),
        )
        mock_upload_bp_metadata.assert_awaited_once_with(submission_id, "mock-userid", "oidc-token")

        # Assert registrations.
        response = nbis_client.get(f"{API_PREFIX}/submissions/{submission_id}/registrations")
        data = response.json()
        assert response.status_code == 200
        registration = Registration.model_validate(data)
        # Check DOI
        assert registration.doi == doi
        # Check that metax ID does not exist
        assert registration.metaxId is None
        # Check REMS
        assert registration.remsResourceId is not None
        assert registration.remsCatalogueId is not None
        assert registration.remsUrl is not None


async def test_publish_submission_bp_fails_when_metadata_upload_fails(
    nbis_client, submission_repository, object_repository, file_repository
):
    """BP publish should fail and remain unpublished if metadata encryption/upload fails."""

    rems = Rems(
        organizationId=MOCK_REMS_DEFAULT_ORGANISATION_ID,
        workflowId=MOCK_REMS_DEFAULT_WORKFLOW_ID,
        licenses=[MOCK_REMS_DEFAULT_LICENSE_ID],
    )

    submission_entity = create_submission_entity(
        workflow=SubmissionWorkflow.BP,
        document={SUB_FIELD_METADATA: SUBMISSION_METADATA, SUB_FIELD_REMS: to_json_dict(rems)},
        bucket="test-bucket",
        title="bp-title",
    )
    submission_id = await submission_repository.add_submission(submission_entity)

    object_entity = create_object_entity(
        project_id=submission_entity.project_id,
        submission_id=submission_id,
        object_type="dataset",
        document={},
        title="bp-title",
        description="bp-description",
    )
    await object_repository.add_object(object_entity, SubmissionWorkflow.BP)

    await file_repository.add_file(
        FileEntity(
            submission_id=submission_id,
            object_id=object_entity.object_id,
            path="test-path",
            bytes=1,
        ),
        SubmissionWorkflow.BP,
    )

    with (
        patch_verify_user_project,
        patch_verify_authorization,
        patch(
            "metadata_backend.api.handlers.publish.PublishAPIHandler._upload_bp_metadata_xmls",
            new_callable=AsyncMock,
            side_effect=SystemException("metadata upload failed"),
        ) as mock_upload_bp_metadata,
        patch(
            "metadata_backend.api.services.file.S3InboxSDAService.check_files_exist", new_callable=AsyncMock
        ) as mock_check_files_exist,
        patch_datacite_create_draft_doi("10.1/test") as _mock_datacite_create_draft_doi,
        patch_datacite_publish() as _mock_datacite_publish,
        patch_rems_create_resource() as _mock_rems_create_resource,
        patch_rems_create_catalogue_item() as _mock_rems_create_catalogue_item,
    ):
        mock_check_files_exist.return_value = []

        response = nbis_client.patch(
            f"{API_PREFIX}/publish/{submission_id}", headers={"Authorization": "Bearer oidc-token"}
        )
        data = response.json()
        assert response.status_code == 500
        assert "metadata upload failed" in data["detail"]
        mock_upload_bp_metadata.assert_awaited_once_with(submission_id, "mock-userid", "oidc-token")

    stored = await submission_repository.get_submission_by_id(submission_id)
    assert stored is not None
    assert not stored.is_published


def test_get_discovery_url_csc():
    submission = Submission(
        projectId="test1",
        submissionId="test2",
        name="test3",
        title="test4",
        description="test4",
        workflow=SubmissionWorkflow.SD,
    )

    # Metax ID

    registration = Registration(
        submissionId=submission.submissionId, title="test5", description="test6", doi="test7", metaxId="test8"
    )
    assert PublishAPIHandler.get_discovery_url(submission, registration) == TEST_DISCOVERY_URL.format(
        id=registration.metaxId
    )

    # DOI

    registration = Registration(submissionId=submission.submissionId, title="test5", description="test6", doi="test7")
    assert PublishAPIHandler.get_discovery_url(submission, registration) == TEST_DISCOVERY_URL.format(
        id=registration.doi
    )

    # submission id

    registration = Registration(submissionId=submission.submissionId, title="test5", description="test6")
    assert PublishAPIHandler.get_discovery_url(submission, registration) == TEST_DISCOVERY_URL.format(
        id=submission.submissionId
    )


def test_get_discovery_url_bp():
    submission = Submission(
        projectId="test1",
        submissionId="test2",
        name="test3",
        title="test4",
        description="test4",
        workflow=SubmissionWorkflow.BP,
    )

    registration = Registration(submissionId=submission.submissionId, title="test5", description="test6")
    assert PublishAPIHandler.get_discovery_url(submission, registration) == TEST_DISCOVERY_URL.format(
        id=submission.submissionId
    )


async def test_upload_bp_metadata_xmls_uses_expected_object_keys_and_payloads():
    """BP metadata upload helper should upload plaintext XML to expected DATASET_{id}/METADATA keys."""

    submission_id = "123"
    file_provider = S3InboxSDAService(AsyncMock())
    file_provider._add_file_to_bucket = AsyncMock()  # type: ignore[method-assign]

    object_docs: dict[str, list[str]] = {
        "dataset": ["<DATASET/>"],
        "policy": ["<POLICY/>"],
        "image": ["<IMAGE/>"],
        "annotation": ["<ANNOTATION/>"],
        "observation": ["<OBSERVATION/>"],
        "observer": ["<OBSERVER/>"],
        "staining": ["<STAINING/>"],
        BP_SAMPLE_OBJECT_TYPES[0]: ["<BIOLOGICAL_BEING/>"],
    }

    def get_xml_documents(_submission_id: str, object_type: str | tuple[str, ...]):
        async def _iter():
            if isinstance(object_type, tuple):
                for sample_type in object_type:
                    for xml in object_docs.get(sample_type, []):
                        yield xml
                return

            for xml in object_docs.get(object_type, []):
                yield xml

        return _iter()

    handler = PublishAPIHandler.__new__(PublishAPIHandler)
    handler._services = SimpleNamespace(
        file_provider=file_provider,
        submission=SimpleNamespace(get_bucket=AsyncMock(return_value="test-bucket")),
        object=SimpleNamespace(get_xml_documents=get_xml_documents),
    )

    await handler._upload_bp_metadata_xmls(submission_id, "request-user", "oidc-token")

    expected_keys = {
        "DATASET_123/METADATA/dataset.xml.c4gh",
        "DATASET_123/METADATA/policy.xml.c4gh",
        "DATASET_123/METADATA/image.xml.c4gh",
        "DATASET_123/METADATA/annotation.xml.c4gh",
        "DATASET_123/METADATA/observation.xml.c4gh",
        "DATASET_123/METADATA/observer.xml.c4gh",
        "DATASET_123/METADATA/sample.xml.c4gh",
        "DATASET_123/METADATA/staining.xml.c4gh",
    }

    assert file_provider._add_file_to_bucket.await_count == len(expected_keys)

    uploaded_keys = {call.kwargs["object_key"] for call in file_provider._add_file_to_bucket.await_args_list}
    assert uploaded_keys == expected_keys
    for call in file_provider._add_file_to_bucket.await_args_list:
        assert call.kwargs["access_key"] == "request-user"
        assert call.kwargs["secret_key"] == "request-user"
        assert call.kwargs["session_token"] == "oidc-token"
        assert isinstance(call.kwargs["body"], bytes)
        assert call.kwargs["body"]


async def test_upload_bp_metadata_xmls_raises_on_upload_error():
    """Upload errors in BP metadata upload helper should fail publish flow."""

    file_provider = S3InboxSDAService(AsyncMock())
    file_provider._add_file_to_bucket = AsyncMock()  # type: ignore[method-assign]

    def get_xml_documents(_submission_id: str, object_type: str | tuple[str, ...]):
        async def _iter():
            if object_type == "dataset":
                yield "<DATASET/>"

        return _iter()

    handler = PublishAPIHandler.__new__(PublishAPIHandler)
    handler._services = SimpleNamespace(
        file_provider=file_provider,
        submission=SimpleNamespace(get_bucket=AsyncMock(return_value="test-bucket")),
        object=SimpleNamespace(get_xml_documents=get_xml_documents),
    )

    file_provider._add_file_to_bucket.side_effect = SystemException("upload failed")  # type: ignore[method-assign]

    with pytest.raises(SystemException, match="upload failed"):
        await handler._upload_bp_metadata_xmls("123", "request-user", "oidc-token")
