"""Tests for publish API handler."""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import ANY, AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from metadata_backend.api.exceptions import SystemException
from metadata_backend.api.handlers.publish import PublishAPIHandler
from metadata_backend.api.handlers.submission import SubmissionAPIHandler
from metadata_backend.api.json import to_json_dict
from metadata_backend.api.models.datacite import Subject
from metadata_backend.api.models.models import Registration
from metadata_backend.api.models.sda import FileItem
from metadata_backend.api.models.submission import Rems, Submission, SubmissionMetadata, SubmissionWorkflow
from metadata_backend.api.processors.xml.bigpicture import BP_DATASET_OBJECT_TYPE, BP_POLICY_OBJECT_TYPE
from metadata_backend.api.services.file import FileProviderService
from metadata_backend.conf.deployment import Deployment, deployment_config
from metadata_backend.database.postgres.models import FileEntity, ObjectEntity, SubmissionEntity
from metadata_backend.database.postgres.repositories.submission import (
    SUB_FIELD_METADATA,
    SUB_FIELD_REMS,
)
from metadata_backend.database.postgres.repository import (
    SessionFactory,
    _session_context,
    committed_session,
    create_engine,
    create_session_factory,
    get_sqllite_db_url,
    session_factory_context,
)
from metadata_backend.database.postgres.services.submission import PublishedSubmissionUserException, SubmissionService
from metadata_backend.server import create_app
from metadata_backend.services.rems_service import RemsServiceHandler
from tests.unit.database.postgres.helpers import create_object_entity, create_submission_entity
from tests.unit.patches.user import patch_verify_authorization, patch_verify_user_project

from ...conftest import TEST_DISCOVERY_URL, set_deployment_env
from ...patches.datacite_service import (
    patch_datacite_create_draft_doi,
    patch_datacite_publish,
)
from ...patches.metax_service import (
    patch_metax_create_draft_dataset,
    patch_metax_publish_dataset,
    patch_metax_update_dataset_description,
    patch_metax_update_dataset_metadata,
    patch_metax_update_dataset_title_and_description,
    patch_metax_validate_dataset_metadata,
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
    mock_rems_existing_catalogue_item,
    mock_rems_resource_id,
    patch_rems_create_catalogue_item,
    patch_rems_create_resource,
    patch_rems_edit_catalogue_item,
)
from .common import SUBMISSION_METADATA

REMS = Rems(
    organizationId=MOCK_REMS_DEFAULT_ORGANISATION_ID,
    workflowId=MOCK_REMS_DEFAULT_WORKFLOW_ID,
    licenses=[MOCK_REMS_DEFAULT_LICENSE_ID],
)


async def _add_bp_submission(submission_repository, **kwargs) -> SubmissionEntity:
    """Add a BP submission with the default REMS information."""
    submission_entity = create_submission_entity(
        workflow=SubmissionWorkflow.BP,
        document={SUB_FIELD_METADATA: SUBMISSION_METADATA, SUB_FIELD_REMS: to_json_dict(REMS)},
        **kwargs,
    )
    await submission_repository.add_submission(submission_entity)
    return submission_entity


async def _add_bp_object(
    object_repository, submission_entity: SubmissionEntity, object_type: str, **kwargs
) -> ObjectEntity:
    """Add a metadata object to a BP submission."""
    object_entity = create_object_entity(
        project_id=submission_entity.project_id,
        submission_id=submission_entity.submission_id,
        object_type=object_type,
        **kwargs,
    )
    await object_repository.add_object(object_entity, SubmissionWorkflow.BP)
    return object_entity


@contextmanager
def _patch_bp_publish(doi: str = "10.1/test") -> Iterator[SimpleNamespace]:
    """Patch every external call made when publishing a BP submission.

    - ProjectService.verify_user_project: accept any project id.
    - middlewares.verify_authorization: accept any user bearer token.
    - generate_bp_metadata_xmls: generate no metadata XMLs to validate before registration.
    - upload_bp_metadata_xmls: upload no metadata XMLs to the SDA inbox.
    - S3InboxSDAService.list_submission_inbox_files: list no files in the SDA inbox.
    - S3InboxSDAService.find_missing_files: no submission file is missing from the SDA inbox.
    - S3InboxSDAService.find_orphaned_files: the SDA inbox has no unexpected files.
    - DataciteServiceHandler.create_draft_doi: create ``doi`` as the draft DOI.
    - DataciteServiceHandler.publish: do not publish the draft DOI in DataCite.
    - RemsServiceHandler.create_resource: create the resource in the mock REMS.
    - RemsServiceHandler.create_catalogue_item: create the catalogue item in the mock REMS.

    Args:
        doi: The DOI DataCite creates for the submission.

    Yields:
        The mocks by name, so that a test can assert their calls or change what they return.
    """
    with (
        patch_verify_user_project,
        patch_verify_authorization,
        patch(
            "metadata_backend.api.services.workflow.generate_bp_metadata_xmls", new=AsyncMock(return_value={})
        ) as generate_bp_metadata,
        patch(
            "metadata_backend.api.services.workflow.upload_bp_metadata_xmls", new_callable=AsyncMock
        ) as upload_bp_metadata,
        patch(
            "metadata_backend.api.services.file.S3InboxSDAService.list_submission_inbox_files",
            new=AsyncMock(return_value=[]),
        ) as list_submission_inbox_files,
        patch(
            "metadata_backend.api.services.file.S3InboxSDAService.find_missing_files", new=AsyncMock(return_value=[])
        ) as find_missing_files,
        patch(
            "metadata_backend.api.services.file.S3InboxSDAService.find_orphaned_files", new=AsyncMock(return_value=[])
        ) as find_orphaned_files,
        patch_datacite_create_draft_doi(doi) as datacite_create_draft_doi,
        patch_datacite_publish() as datacite_publish,
        patch_rems_create_resource() as rems_create_resource,
        patch_rems_create_catalogue_item() as rems_create_catalogue_item,
        patch_rems_edit_catalogue_item() as rems_edit_catalogue_item,
    ):
        yield SimpleNamespace(
            generate_bp_metadata=generate_bp_metadata,
            upload_bp_metadata=upload_bp_metadata,
            list_submission_inbox_files=list_submission_inbox_files,
            find_missing_files=find_missing_files,
            find_orphaned_files=find_orphaned_files,
            datacite_create_draft_doi=datacite_create_draft_doi,
            datacite_publish=datacite_publish,
            rems_create_resource=rems_create_resource,
            rems_create_catalogue_item=rems_create_catalogue_item,
            rems_edit_catalogue_item=rems_edit_catalogue_item,
        )


async def test_publish_submission_sd(csc_client, submission_repository, object_repository, file_repository):
    """Test publishing of CSC submission."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1

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
        response = csc_client.patch(f"{api_prefix_v1}/publish/{submission_id}")
        data = response.json()
        assert response.status_code == 400
        assert data["detail"] == "User error"
        assert data["errors"] == [f"Submission '{submission_id}' is not linked to any bucket."]

    file_provider_cls = "metadata_backend.api.services.file.FileProviderService"

    with (
        patch_verify_user_project,
        patch_verify_authorization,
        patch(
            "metadata_backend.api.services.workflow.upload_bp_metadata_xmls",
            new_callable=AsyncMock,
        ) as mock_upload_bp_metadata,
        # File provider
        patch(f"{file_provider_cls}.list_files_in_bucket", new_callable=AsyncMock) as mock_file_provider,
        patch_pid_create_draft_doi(doi) as mock_pid_create_draft_doi,
        patch_pid_publish() as mock_pid_publish,
        # Metax
        patch_metax_create_draft_dataset(metax_id) as mock_metax_create_draft_dataset,
        patch_metax_update_dataset_metadata() as mock_metax_update_dataset_metadata,
        patch_metax_validate_dataset_metadata() as mock_metax_validate_dataset_metadata,
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
            document={SUB_FIELD_METADATA: SUBMISSION_METADATA, SUB_FIELD_REMS: to_json_dict(REMS)},
            bucket="test-bucket",
        )

        # Test edge case where file service has not received any files.
        submission_id = await submission_repository.add_submission(submission_entity)
        mock_file_provider.return_value = FileProviderService.Files(root=[])
        response = csc_client.patch(f"{api_prefix_v1}/publish/{submission_id}")
        data = response.json()
        assert response.status_code == 400
        assert data["detail"] == "User error"
        assert data["errors"] == [f"Submission '{submission_id}' does not have any data files."]

        # Mock file provider
        mock_file_provider.return_value = FileProviderService.Files(
            [FileProviderService.File(path=file_path, bytes=file_bytes)]
        )

        # Publish submission.
        response = csc_client.patch(f"{api_prefix_v1}/publish/{submission_id}")
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

        mock_metax_validate_dataset_metadata.assert_awaited_once()
        mock_metax_update_dataset_metadata.assert_awaited_once()
        mock_metax_update_dataset_description.assert_awaited_once_with(
            metax_id,
            f"{submission_description}\n\nSD Apply Application link: "
            f"{RemsServiceHandler.get_application_url(str(mock_rems_catalogue_id))}",
        )

        mock_metax_publish_dataset.assert_awaited_once_with(metax_id, doi)

        # Assert Rems.
        mock_rems_create_resource.assert_awaited_once_with(REMS.organizationId, REMS.licenses, doi)
        mock_rems_create_catalogue_item.assert_awaited_once_with(
            REMS.organizationId,
            REMS.workflowId,
            mock_rems_resource_id,
            submission_title,
            TEST_DISCOVERY_URL.format(id=metax_id),
        )

        # BP metadata upload should never run for SD workflow.
        mock_upload_bp_metadata.assert_not_awaited()


async def test_publish_submission_bp(nbis_client, submission_repository, object_repository, file_repository):
    """Test publishing of BP submission."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1

    # The submission contains one dataset metadata object and one file.
    dataset_title = f"title_{str(uuid.uuid4())}"
    submission_entity = await _add_bp_submission(submission_repository, bucket="test-bucket", title=dataset_title)
    submission_id = submission_entity.submission_id
    object_entity = await _add_bp_object(
        object_repository,
        submission_entity,
        BP_DATASET_OBJECT_TYPE,
        title=dataset_title,
        description=f"description_{str(uuid.uuid4())}",
    )
    await file_repository.add_file(
        FileEntity(
            submission_id=submission_id,
            object_id=object_entity.object_id,
            path=f"path_{str(uuid.uuid4())}",
            bytes=1024,
        ),
        SubmissionWorkflow.BP,
    )

    doi = f"doi_{str(uuid.uuid4())}/doi_{str(uuid.uuid4())}"

    with (
        _patch_bp_publish(doi) as mocks,
        patch_pid_create_draft_doi(doi) as mock_pid_create_draft_doi,
        patch_pid_publish() as mock_pid_publish,
    ):
        # Records the order of the calls to these mocks.
        call_order = Mock()
        call_order.attach_mock(mocks.generate_bp_metadata, "generate_bp_metadata_xmls")
        call_order.attach_mock(mocks.datacite_create_draft_doi, "create_draft_doi")
        call_order.attach_mock(mocks.rems_create_catalogue_item, "create_catalogue_item")
        call_order.attach_mock(mocks.upload_bp_metadata, "upload_bp_metadata_xmls")

        # Publish submission.
        response = nbis_client.patch(
            f"{api_prefix_v1}/publish/{submission_id}", headers={"Authorization": "Bearer oidc-token"}
        )
        data = response.json()
        assert response.status_code == 200
        assert data == {"submissionId": submission_id}

        mocks.datacite_create_draft_doi.assert_awaited_once()
        mocks.datacite_publish.assert_awaited_once()
        mock_pid_create_draft_doi.assert_not_awaited()
        mock_pid_publish.assert_not_awaited()

        # Assert Beacon.
        # TODO(improve): BP beacon service not implement

        # Assert Rems.
        mocks.rems_create_resource.assert_awaited_once_with(REMS.organizationId, REMS.licenses, submission_id)
        mocks.rems_create_catalogue_item.assert_awaited_once_with(
            REMS.organizationId,
            REMS.workflowId,
            1,  # REMS resource id
            f"{submission_entity.name} ({REMS.organizationId}, {submission_id})",
            TEST_DISCOVERY_URL.format(id=submission_id),
        )
        mocks.list_submission_inbox_files.assert_awaited_once_with("mock-userid", submission_id)
        mocks.upload_bp_metadata.assert_awaited_once_with(ANY, submission_id, "mock-userid", "oidc-token")

        # Assert the call order of XML generation for validation, registration and XML generation for upload. Only the
        # generation for upload adds the DOI and REMS links to the landing page XML.
        assert [name for name, _args, _kwargs in call_order.mock_calls] == [
            "generate_bp_metadata_xmls",
            "create_draft_doi",
            "create_catalogue_item",
            "upload_bp_metadata_xmls",
        ]

        # Assert registrations.
        response = nbis_client.get(f"{api_prefix_v1}/submissions/{submission_id}/registrations")
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


async def test_publish_submission_bp_non_clinical(nbis_client, submission_repository, object_repository):
    """Test publishing of a non-clinical BP submission.

    A non-clinical dataset is not registered in REMS.
    """

    api_prefix_v1 = deployment_config().API_PREFIX_V1

    submission_entity = await _add_bp_submission(submission_repository, metadata_version="2.0")
    submission_id = submission_entity.submission_id
    await _add_bp_object(
        object_repository,
        submission_entity,
        BP_DATASET_OBJECT_TYPE,
        document="<DATASET><METADATA_STANDARD>2.0.0</METADATA_STANDARD></DATASET>",
    )
    # The policy says the dataset is non-clinical.
    await _add_bp_object(
        object_repository,
        submission_entity,
        BP_POLICY_OBJECT_TYPE,
        document='<POLICY alias="1"><DATASET_REF alias="1"/><ATTRIBUTES>'
        "<STRING_ATTRIBUTE><TAG>type_of_dataset</TAG><VALUE>Non-Clinical/Obscured</VALUE></STRING_ATTRIBUTE>"
        "</ATTRIBUTES></POLICY>",
    )

    with _patch_bp_publish() as mocks:
        response = nbis_client.patch(
            f"{api_prefix_v1}/publish/{submission_id}", headers={"Authorization": "Bearer oidc-token"}
        )

        assert response.status_code == 200, response.text
        assert response.json() == {"submissionId": submission_id}

        # Nothing of the submission reaches REMS.
        mocks.rems_create_resource.assert_not_awaited()
        mocks.rems_create_catalogue_item.assert_not_awaited()

        response = nbis_client.get(f"{api_prefix_v1}/submissions/{submission_id}/registrations")
        assert response.status_code == 200
        registration = Registration.model_validate(response.json())
        assert registration.remsResourceId is None
        assert registration.remsCatalogueId is None
        assert registration.remsUrl is None


async def test_publish_submission_bp_invalid_stored_policy(nbis_client, submission_repository, object_repository):
    """Test that an invalid stored policy XML is a server error, not a user error."""

    api_prefix_v1 = deployment_config().API_PREFIX_V1

    submission_entity = await _add_bp_submission(submission_repository, metadata_version="2.0")
    submission_id = submission_entity.submission_id
    await _add_bp_object(
        object_repository,
        submission_entity,
        BP_DATASET_OBJECT_TYPE,
        document="<DATASET><METADATA_STANDARD>2.0.0</METADATA_STANDARD></DATASET>",
    )
    # The stored policy is not well-formed XML.
    await _add_bp_object(object_repository, submission_entity, BP_POLICY_OBJECT_TYPE, document="<POLICY>")

    with _patch_bp_publish():
        response = nbis_client.patch(
            f"{api_prefix_v1}/publish/{submission_id}", headers={"Authorization": "Bearer oidc-token"}
        )

        assert response.status_code == 500, response.text
        problem_json = response.json()
        assert problem_json["detail"].startswith("Premature end of data in tag POLICY")
        assert "errors" not in problem_json

    stored = await submission_repository.get_submission_by_id(submission_id)
    assert stored is not None
    assert not stored.is_published


@pytest.mark.parametrize(
    ("client_fixture", "workflow"),
    [
        pytest.param("csc_client", SubmissionWorkflow.BP, id="bp_submission_in_sd_deployment"),
        pytest.param("nbis_client", SubmissionWorkflow.SD, id="sd_submission_in_bp_deployment"),
    ],
)
@pytest.mark.parametrize("no_files", [False, True])
async def test_publish_submission_of_other_workflow(request, submission_repository, client_fixture, workflow, no_files):
    """Test that a deployment does not publish a submission of another workflow."""

    client = request.getfixturevalue(client_fixture)
    api_prefix_v1 = deployment_config().API_PREFIX_V1

    submission_id = await submission_repository.add_submission(
        create_submission_entity(
            workflow=workflow, metadata_version="2.0" if workflow == SubmissionWorkflow.BP else None
        )
    )

    with (
        patch_verify_user_project,
        patch_verify_authorization,
        patch("metadata_backend.api.handlers.publish.workflow_profile") as mock_workflow_profile,
    ):
        response = client.patch(f"{api_prefix_v1}/publish/{submission_id}?no_files={str(no_files).lower()}")
        assert response.status_code == 400
        assert f"Submission belongs to a different workflow: '{workflow.value}'" in response.text
        mock_workflow_profile.assert_not_called()

        response = client.get(f"{api_prefix_v1}/submissions/{submission_id}")
        assert response.status_code == 200
        assert not Submission.model_validate(response.json()).published


async def test_publish_submission_lock(csc_client, submission_repository):
    """Test that publish checks access before locking the submission, and the published state again after."""

    api_prefix_v1 = deployment_config().API_PREFIX_V1
    submission_id = await submission_repository.add_submission(create_submission_entity())

    # The mocks are children of calls, which records their calls in order.
    calls = AsyncMock()
    calls.check_not_published.side_effect = PublishedSubmissionUserException(submission_id)
    with (
        patch_verify_user_project,
        patch_verify_authorization,
        patch.object(SubmissionAPIHandler, "check_submission_modifiable", new=calls.check_submission_modifiable),
        patch.object(SubmissionService, "lock_submission", new=calls.lock_submission),
        patch.object(SubmissionService, "check_not_published", new=calls.check_not_published),
    ):
        response = csc_client.patch(f"{api_prefix_v1}/publish/{submission_id}?no_files=true")

    assert response.status_code == 400
    # Access is checked before the lock, so that only users who can modify the submission hold it.
    # The published state is checked again after the lock, since a concurrent publish may have
    # finished between the access check and the lock.
    assert [name for name, *_ in calls.mock_calls] == [
        "check_submission_modifiable",
        "lock_submission",
        "check_not_published",
    ]


@pytest.mark.parametrize(
    ("published_to_rems", "licenses", "license_created"),
    [
        (True, [], True),
        (True, [MOCK_REMS_DEFAULT_LICENSE_ID], False),
        (False, [], False),
    ],
)
async def test_check_rems_license(published_to_rems, licenses, license_created):
    """Test that the REMS license is checked only when it is created from the policy."""

    license_provider = AsyncMock()
    handler = PublishAPIHandler(SimpleNamespace(license_provider=license_provider), SimpleNamespace())
    rems = Rems(organizationId="org", workflowId=1, licenses=licenses)

    with patch.object(handler, "_is_published_to_rems", AsyncMock(return_value=published_to_rems)):
        await handler._check_rems_license(SimpleNamespace(submissionId="submission"), rems)

    assert license_provider.get_license.await_count == (1 if license_created else 0)


async def test_publish_submission_bp_fails_when_metadata_upload_fails(
    nbis_client, submission_repository, object_repository, file_repository
):
    """BP publish should fail and remain unpublished if metadata encryption/upload fails."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1

    submission_entity = await _add_bp_submission(submission_repository, bucket="test-bucket", title="bp-title")
    submission_id = submission_entity.submission_id
    object_entity = await _add_bp_object(
        object_repository, submission_entity, BP_DATASET_OBJECT_TYPE, title="bp-title", description="bp-description"
    )
    await file_repository.add_file(
        FileEntity(
            submission_id=submission_id,
            object_id=object_entity.object_id,
            path="test-path",
            bytes=1,
        ),
        SubmissionWorkflow.BP,
    )

    with _patch_bp_publish() as mocks:
        mocks.upload_bp_metadata.side_effect = SystemException("metadata upload failed")

        response = nbis_client.patch(
            f"{api_prefix_v1}/publish/{submission_id}", headers={"Authorization": "Bearer oidc-token"}
        )
        data = response.json()
        assert response.status_code == 500
        assert "metadata upload failed" in data["detail"]
        mocks.upload_bp_metadata.assert_awaited_once_with(ANY, submission_id, "mock-userid", "oidc-token")

    stored = await submission_repository.get_submission_by_id(submission_id)
    assert stored is not None
    assert not stored.is_published


async def test_publish_submission_bp_invalid_metadata_fails_before_registration(
    nbis_client, submission_repository, object_repository, file_repository
):
    """BP publish fails on an invalid metadata XML before registering a DOI or uploading anything."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1

    submission_entity = await _add_bp_submission(submission_repository, bucket="test-bucket", title="bp-title")
    submission_id = submission_entity.submission_id
    object_entity = await _add_bp_object(
        object_repository, submission_entity, BP_DATASET_OBJECT_TYPE, title="bp-title", description="bp-description"
    )
    await file_repository.add_file(
        FileEntity(submission_id=submission_id, object_id=object_entity.object_id, path="test-path", bytes=1),
        SubmissionWorkflow.BP,
    )

    with _patch_bp_publish() as mocks:
        mocks.generate_bp_metadata.side_effect = SystemException("Generated XML document is not valid")

        response = nbis_client.patch(
            f"{api_prefix_v1}/publish/{submission_id}", headers={"Authorization": "Bearer oidc-token"}
        )
        assert response.status_code == 500

        mocks.datacite_create_draft_doi.assert_not_awaited()
        mocks.upload_bp_metadata.assert_not_awaited()

    stored = await submission_repository.get_submission_by_id(submission_id)
    assert stored is not None
    assert not stored.is_published


async def test_publish_submission_bp_adds_thumbnail_jpgs_before_orphan_check(
    nbis_client, submission_repository, object_repository, file_repository, caplog
):
    """BP publish should add landing page thumbnail JPG files to submission but not other unexpected files."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    caplog.set_level("INFO", logger="server")

    submission_entity = await _add_bp_submission(submission_repository, bucket="test-bucket", title="bp-title")
    submission_id = submission_entity.submission_id
    object_entity = await _add_bp_object(
        object_repository, submission_entity, BP_DATASET_OBJECT_TYPE, title="bp-title", description="bp-description"
    )

    existing_path = f"{submission_id}/IMAGES/IMAGE_1/img1.dcm.c4gh"
    thumbnail_jpg_path = f"DATASET_{submission_id}/LANDING_PAGE/THUMBNAILS/thumb.jpg.c4gh"
    unencrypted_path = f"DATASET_{submission_id}/LANDING_PAGE/THUMBNAILS/thumb.jpg"
    unexpected_path = f"{submission_id}/LANDING_PAGE/unexpected.txt"

    # File which represents submission file parsed from XML upload and should exist in the inbox at publish time.
    await file_repository.add_file(
        FileEntity(
            submission_id=submission_id,
            object_id=object_entity.object_id,
            path=existing_path,
            bytes=1,
        ),
        SubmissionWorkflow.BP,
    )

    with _patch_bp_publish() as mocks:
        # thumbnail_jpg_path should be added to submission files before the orphaned files check
        mocks.list_submission_inbox_files.return_value = [
            FileItem(
                fileID="12345678-1234-4234-8234-1234567890ab",
                inboxPath=thumbnail_jpg_path,
                fileStatus="uploaded",
                createdAt="2024-01-01T00:00:00Z",
            ),
            FileItem(
                fileID="22345678-1234-4234-8234-1234567890ab",
                inboxPath=unencrypted_path,
                fileStatus="uploaded",
                createdAt="2024-01-01T00:00:00Z",
            ),
            FileItem(
                fileID="32345678-1234-4234-8234-1234567890ab",
                inboxPath=unexpected_path,
                fileStatus="uploaded",
                createdAt="2024-01-01T00:00:00Z",
            ),
        ]
        # unencrypted_path and unexpected_path should not be added to submission files and are thus orphaned files
        mocks.find_orphaned_files.side_effect = lambda _user_id, _submission_id, files: [
            path for path in [unencrypted_path, unexpected_path] if path not in {file.path for file in files}
        ]

        response = nbis_client.patch(
            f"{api_prefix_v1}/publish/{submission_id}", headers={"Authorization": "Bearer oidc-token"}
        )
        data = response.json()

        assert response.status_code == 400
        assert data["detail"] == "User error"
        assert data["errors"] == [
            f"Unexpected files found in the inbox for submission '{submission_id}': "
            f"{unencrypted_path}, {unexpected_path}."
        ]

        mocks.find_missing_files.assert_awaited_once()
        orphan_call = mocks.find_orphaned_files.await_args
        checked_paths = {file.path for file in orphan_call.args[2]}
        assert thumbnail_jpg_path in checked_paths
        assert unencrypted_path not in checked_paths

    assert await file_repository.get_file_by_path(submission_id, thumbnail_jpg_path) is not None
    assert await file_repository.get_file_by_path(submission_id, unencrypted_path) is None
    # The thumbnails added are logged once in total.
    info = [r.getMessage() for r in caplog.records if r.levelname == "INFO" and "thumbnail" in r.getMessage()]
    assert info == [f"Added 1 thumbnail file(s) to submission '{submission_id}'"]


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


@pytest.mark.parametrize("is_imported", [False, True])
async def test_publish_submission_bp_reuses_rems(
    nbis_client, submission_repository, object_repository, caplog, is_imported
):
    """Test that publishing a BP submission reuses the REMS resource and catalogue item of its dataset.

    The catalogue item is renamed to the registration title, unless the dataset was imported.
    """
    api_prefix_v1 = deployment_config().API_PREFIX_V1

    submission_entity = await _add_bp_submission(submission_repository, bucket="test-bucket", is_imported=is_imported)
    submission_id = submission_entity.submission_id
    await _add_bp_object(object_repository, submission_entity, BP_DATASET_OBJECT_TYPE)

    with mock_rems_existing_catalogue_item(submission_id) as (resource, item), _patch_bp_publish() as mocks:
        response = nbis_client.patch(
            f"{api_prefix_v1}/publish/{submission_id}?no_files=true", headers={"Authorization": "Bearer oidc-token"}
        )
        assert response.status_code == 200, response.text
        mocks.rems_create_resource.assert_not_awaited()
        mocks.rems_create_catalogue_item.assert_not_awaited()

        response = nbis_client.get(f"{api_prefix_v1}/submissions/{submission_id}/registrations")
        registration = Registration.model_validate(response.json())
        assert registration.remsResourceId == str(resource.id)
        assert registration.remsCatalogueId == str(item.id)

        if is_imported:
            mocks.rems_edit_catalogue_item.assert_not_awaited()
        else:
            mocks.rems_edit_catalogue_item.assert_awaited_once_with(
                item.id, registration.title, TEST_DISCOVERY_URL.format(id=submission_id)
            )

    assert f"keeping its licenses [{MOCK_REMS_DEFAULT_LICENSE_ID}]" in caplog.text


async def test_publish_submission_bp_rems_catalogue_item_without_resource(
    nbis_client, submission_repository, object_repository
):
    """Test that a REMS catalogue item without an active resource fails publishing before a resource is created."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1

    submission_entity = await _add_bp_submission(submission_repository, bucket="test-bucket")
    submission_id = submission_entity.submission_id
    await _add_bp_object(object_repository, submission_entity, BP_DATASET_OBJECT_TYPE)

    with (
        mock_rems_existing_catalogue_item(submission_id) as (resource, item),
        # The catalogue item's resource is no longer active, so REMS lists no resource.
        patch.object(RemsServiceHandler, "get_resources", new=AsyncMock(return_value=[])),
        _patch_bp_publish() as mocks,
    ):
        response = nbis_client.patch(
            f"{api_prefix_v1}/publish/{submission_id}?no_files=true", headers={"Authorization": "Bearer oidc-token"}
        )
        assert response.status_code == 400, response.text
        assert response.json()["errors"] == [
            f"REMS catalogue item '{item.id}' belongs to REMS resource '{resource.id}', not to an active REMS resource."
        ]
        mocks.rems_create_resource.assert_not_awaited()
        mocks.rems_create_catalogue_item.assert_not_awaited()


@asynccontextmanager
async def _transactional_client(
    monkeypatch, tmp_path, deployment: Deployment
) -> AsyncIterator[tuple[TestClient, SessionFactory]]:
    """Run the app with a database transaction per registration request, as in production.

    A temporary database is used, since the test session keeps a write transaction open
    on the shared SQLLite database, which would block the registration transactions.

    Yields the client, and the session factory with which the test writes and reads the database.
    """
    monkeypatch.setenv("DATABASE_URL", get_sqllite_db_url(str(tmp_path / "publish.db")))
    set_deployment_env(monkeypatch, deployment)

    engine = await create_engine()
    token = _session_context.set(None)
    try:
        with (
            # Stop the NBIS ingest scanner, which would otherwise ingest the published submission during the test.
            patch("metadata_backend.api.services.ingest.SDAIngestService.run_forever", new_callable=AsyncMock),
            TestClient(create_app()) as client,
        ):
            yield client, create_session_factory(engine)
    finally:
        _session_context.reset(token)
        await engine.dispose()


@asynccontextmanager
async def _committed_session(session_factory: SessionFactory) -> AsyncIterator[None]:
    """Read and write the test database in a committed transaction."""

    # Set the session factory for the publish registrations.
    token = session_factory_context.set(session_factory)
    try:
        async with committed_session():
            yield
    finally:
        session_factory_context.reset(token)


async def _add_sd_submission(submission_repository) -> str:
    """Add a SD submission with the default REMS information."""
    return await submission_repository.add_submission(
        create_submission_entity(document={SUB_FIELD_METADATA: SUBMISSION_METADATA, SUB_FIELD_REMS: to_json_dict(REMS)})
    )


@contextmanager
def _patch_sd_publish(doi: str = "10.1/test") -> Iterator[SimpleNamespace]:
    """Patch every external call made when publishing a SD submission without files.

    Yields:
        The mocks by name, so that a test can assert their calls.
    """
    with (
        patch_verify_user_project,
        patch_verify_authorization,
        patch_pid_create_draft_doi(doi) as pid_create_draft_doi,
        patch_pid_publish() as pid_publish,
        patch_metax_create_draft_dataset("metax_id") as metax_create_draft_dataset,
        patch_metax_validate_dataset_metadata(),
        patch_metax_update_dataset_metadata(),
        patch_metax_update_dataset_description(),
        patch_metax_update_dataset_title_and_description() as metax_update_dataset_title_and_description,
        patch_metax_publish_dataset(),
        patch_rems_create_resource() as rems_create_resource,
        patch_rems_create_catalogue_item() as rems_create_catalogue_item,
        patch_rems_edit_catalogue_item() as rems_edit_catalogue_item,
    ):
        yield SimpleNamespace(
            pid_create_draft_doi=pid_create_draft_doi,
            pid_publish=pid_publish,
            metax_create_draft_dataset=metax_create_draft_dataset,
            metax_update_dataset_title_and_description=metax_update_dataset_title_and_description,
            rems_create_resource=rems_create_resource,
            rems_create_catalogue_item=rems_create_catalogue_item,
            rems_edit_catalogue_item=rems_edit_catalogue_item,
        )


async def _fail_and_retry_publish(
    client: TestClient,
    submission_id: str,
    target: str,
    params: dict[str, str] | None = None,
    before_retry: Callable[[], Awaitable[None]] | None = None,
    **kwargs: Any,
) -> Registration:
    """Publish the submission with the target failing, check that it is left unpublished, and publish it again.

    :param client: The test client.
    :param submission_id: The submission id.
    :param target: The import path of the function that fails on the first publish.
    :param params: The query parameters of the publish requests.
    :param before_retry: Called after the failed publish, for example to change the submission.
    :param kwargs: The keyword arguments of every request, for example the headers.
    :returns: The registration after the second publish.
    """
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    publish_url = f"{api_prefix_v1}/publish/{submission_id}"

    # The step fails on the first publish, and the request transaction is rolled back.
    with patch(target, new=AsyncMock(side_effect=SystemException("Unavailable"))):
        assert client.patch(publish_url, params=params, **kwargs).status_code == 500
    assert client.get(f"{api_prefix_v1}/submissions/{submission_id}", **kwargs).json()["published"] is False

    if before_retry is not None:
        await before_retry()

    # The retry resumes from the stored registration.
    assert client.patch(publish_url, params=params, **kwargs).status_code == 200
    response = client.get(f"{api_prefix_v1}/submissions/{submission_id}/registrations", **kwargs)
    return Registration.model_validate(response.json())


@pytest.mark.parametrize(
    "target",
    [
        "metadata_backend.services.metax_service.MetaxServiceHandler.create_draft_dataset",
        "metadata_backend.services.pid_service.PIDServiceHandler.publish",
        "metadata_backend.services.metax_service.MetaxServiceHandler.update_dataset_metadata",
        "metadata_backend.services.rems_service.RemsServiceHandler.create_resource",
        "metadata_backend.services.rems_service.RemsServiceHandler.create_catalogue_item",
        "metadata_backend.services.metax_service.MetaxServiceHandler.update_dataset_description",
        "metadata_backend.services.metax_service.MetaxServiceHandler.publish_dataset",
        "metadata_backend.database.postgres.services.submission.SubmissionService.publish",
    ],
)
async def test_publish_submission_sd_retry(monkeypatch, tmp_path, submission_repository, target):
    """Test that a SD publish retried after a failed registration step does not create external identifier twice."""

    doi = f"10.1/{uuid.uuid4()}"

    async with _transactional_client(monkeypatch, tmp_path, Deployment.CSC) as (client, session_factory):
        async with _committed_session(session_factory):
            submission_id = await _add_sd_submission(submission_repository)

        with _patch_sd_publish(doi) as mocks:
            registration = await _fail_and_retry_publish(client, submission_id, target, params={"no_files": "true"})

    mocks.pid_create_draft_doi.assert_awaited_once()
    mocks.metax_create_draft_dataset.assert_awaited_once()
    mocks.rems_create_resource.assert_awaited_once()
    mocks.rems_create_catalogue_item.assert_awaited_once()
    mocks.metax_update_dataset_title_and_description.assert_not_awaited()
    mocks.rems_edit_catalogue_item.assert_not_awaited()

    assert registration.doi == doi
    assert registration.metaxId == "metax_id"
    assert registration.remsUrl is not None


@pytest.mark.parametrize(
    "target",
    [
        "metadata_backend.services.datacite_service.DataciteServiceHandler.publish",
        "metadata_backend.services.rems_service.RemsServiceHandler.create_resource",
        "metadata_backend.services.rems_service.RemsServiceHandler.create_catalogue_item",
        "metadata_backend.api.services.workflow.upload_bp_metadata_xmls",
        "metadata_backend.database.postgres.services.submission.SubmissionService.publish",
    ],
)
async def test_publish_submission_bp_retry(monkeypatch, tmp_path, submission_repository, target):
    """Test that a BP publish retried after a failed registration step does not create external identifier twice."""

    doi = f"10.1/{uuid.uuid4()}"

    async with _transactional_client(monkeypatch, tmp_path, Deployment.NBIS) as (client, session_factory):
        async with _committed_session(session_factory):
            submission_entity = await _add_bp_submission(submission_repository)
            submission_id = submission_entity.submission_id

        with _patch_bp_publish(doi) as mocks:
            registration = await _fail_and_retry_publish(
                client, submission_id, target, headers={"Authorization": "Bearer oidc-token"}
            )

            mocks.datacite_create_draft_doi.assert_awaited_once()
            mocks.rems_create_resource.assert_awaited_once()
            mocks.rems_create_catalogue_item.assert_awaited_once()

    assert registration.doi == doi
    assert registration.dataciteUrl is not None
    assert registration.remsUrl is not None


async def test_publish_submission_sd_retry_changed(monkeypatch, tmp_path, submission_repository):
    """Test that a SD publish retried after the submission is changed updates the registrations."""

    async def change_submission(submission: SubmissionEntity) -> None:
        submission.title = "New title"
        submission.description = "New description"
        submission.document = {**submission.document, "title": "New title", "description": "New description"}

    async with _transactional_client(monkeypatch, tmp_path, Deployment.CSC) as (client, session_factory):
        async with _committed_session(session_factory):
            submission_id = await _add_sd_submission(submission_repository)

        async def before_retry() -> None:
            async with _committed_session(session_factory):
                await submission_repository.update_submission(submission_id, change_submission)

        with _patch_sd_publish() as mocks:
            # The publish fails after the REMS URL has been added to the Metax description.
            registration = await _fail_and_retry_publish(
                client,
                submission_id,
                "metadata_backend.services.metax_service.MetaxServiceHandler.publish_dataset",
                params={"no_files": "true"},
                before_retry=before_retry,
            )

    mocks.metax_update_dataset_title_and_description.assert_awaited_once_with(
        "metax_id", "New title", f"New description\n\nSD Apply Application link: {registration.remsUrl}"
    )

    # The findable DOI is updated without the publish event.
    assert [call.kwargs["make_findable"] for call in mocks.pid_publish.await_args_list] == [True, False]
    doi_registration = mocks.pid_publish.await_args.args[0]
    assert (doi_registration.title, doi_registration.description) == ("New title", "New description")

    mocks.rems_create_catalogue_item.assert_awaited_once()
    mocks.rems_edit_catalogue_item.assert_awaited_once_with(
        int(registration.remsCatalogueId), "New title", TEST_DISCOVERY_URL.format(id="metax_id")
    )
    assert registration.title == "New title"
    assert registration.description == "New description"
