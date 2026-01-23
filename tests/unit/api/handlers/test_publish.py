"""Tests for publish API handler."""

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from metadata_backend.api.json import to_json_dict
from metadata_backend.api.models.datacite import Subject
from metadata_backend.api.models.models import Registration
from metadata_backend.api.models.submission import Rems, SubmissionMetadata, SubmissionWorkflow
from metadata_backend.api.services.file import FileProviderService
from metadata_backend.conf.conf import API_PREFIX
from metadata_backend.database.postgres.models import FileEntity
from metadata_backend.database.postgres.repositories.file import FileRepository
from metadata_backend.database.postgres.repositories.object import ObjectRepository
from metadata_backend.database.postgres.repositories.submission import (
    SUB_FIELD_METADATA,
    SUB_FIELD_REMS,
    SubmissionRepository,
)
from metadata_backend.services.rems_service import RemsServiceHandler
from tests.unit.database.postgres.helpers import create_object_entity, create_submission_entity

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
from .common import HandlersTestCase


class PublishAPIHandlerTestCaseSD(HandlersTestCase):
    """Test publish handler for SD submissions at CSC."""

    @classmethod
    def setUpClass(cls):
        cls._env_patch = patch.dict(os.environ, {"DEPLOYMENT": "CSC"})
        cls._env_patch.start()
        super().setUpClass()

    @pytest.fixture(autouse=True)
    def _inject_fixtures(
        self,
        submission_repository: SubmissionRepository,
        object_repository: ObjectRepository,
        file_repository: FileRepository,
    ):
        self.submission_repository = submission_repository
        self.object_repository = object_repository
        self.file_repository = file_repository

    async def test_publish_submission_sd(self):
        """Test publishing of CSC submission."""

        submission_metadata = self.submission_metadata

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
        with self.patch_verify_user_project, self.patch_verify_authorization:
            # Create submission without bucket.
            submission_entity = create_submission_entity()
            submission_id = await self.submission_repository.add_submission(submission_entity)
            response = await self.client.patch(f"{API_PREFIX}/publish/{submission_id}")
            data = await response.json()
            assert response.status == 400
            assert data["detail"] == f"Submission '{submission_id}' is not linked to any bucket."

        file_provider_cls = "metadata_backend.api.services.file.FileProviderService"

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
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
                document={SUB_FIELD_METADATA: submission_metadata, SUB_FIELD_REMS: to_json_dict(rems)},
                bucket="test-bucket",
            )

            # Test edge case where file service has not received any files.
            submission_id = await self.submission_repository.add_submission(submission_entity)
            mock_file_provider.return_value = FileProviderService.Files(root=[])
            response = await self.client.patch(f"{API_PREFIX}/publish/{submission_id}")
            data = await response.json()
            assert response.status == 400
            assert data["detail"] == f"Submission '{submission_id}' does not have any data files."

            # Mock file provider
            mock_file_provider.return_value = FileProviderService.Files(
                [FileProviderService.File(path=file_path, bytes=file_bytes)]
            )

            # Publish submission.
            response = await self.client.patch(f"{API_PREFIX}/publish/{submission_id}")
            data = await response.json()
            assert response.status == 200
            assert data == {"submissionId": submission_id}

            mock_pid_create_draft_doi.assert_awaited_once()
            mock_pid_publish.assert_awaited_once()

            # Assert Metax.
            mock_metax_create_draft_dataset.assert_awaited_once_with(doi, submission_title, submission_description)

            expected_submission_metadata = SubmissionMetadata.model_validate(submission_metadata)
            expected_submission_metadata.subjects = [
                Subject(
                    **s,
                    subjectScheme="Korkeakoulujen tutkimustiedonkeruussa käytettävä tieteenalaluokitus",
                    schemeUri="http://www.yso.fi/onto/okm-tieteenala/conceptscheme",
                    valueUri=f"http://www.yso.fi/onto/okm-tieteenala/ta{s['subject'].split(' - ')[0]}",
                    classificationCode=s["subject"].split(" - ")[0],
                )
                for s in submission_metadata.get("subjects", [])
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
                RemsServiceHandler().get_discovery_url(metax_id),
            )


class PublishAPIHandlerTestCaseBP(HandlersTestCase):
    """Test publish handler for BigPicture submissions at NBIS."""

    @classmethod
    def setUpClass(cls):
        cls._env_patch = patch.dict(os.environ, {"DEPLOYMENT": "NBIS"})
        cls._env_patch.start()
        super().setUpClass()

    @pytest.fixture(autouse=True)
    def _inject_fixtures(
        self,
        submission_repository: SubmissionRepository,
        object_repository: ObjectRepository,
        file_repository: FileRepository,
    ):
        self.submission_repository = submission_repository
        self.object_repository = object_repository
        self.file_repository = file_repository

    async def test_publish_submission_nbis(self):
        """Test publishing of BP submission."""

        submission_metadata = self.submission_metadata

        # RENS information.
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
            document={SUB_FIELD_METADATA: submission_metadata, SUB_FIELD_REMS: to_json_dict(rems)},
            bucket="test-bucket",
            title=dataset_title,
        )
        submission_id = await self.submission_repository.add_submission(submission_entity)

        # Create metadata object.
        object_entity = create_object_entity(
            project_id=submission_entity.project_id,
            submission_id=submission_id,
            object_type=dataset_object_type,
            document={},
            title=dataset_title,
            description=dataset_description,
        )
        await self.object_repository.add_object(object_entity, workflow)

        # Create file.
        file_entity = FileEntity(
            submission_id=submission_id,
            object_id=object_entity.object_id,
            path=file_path,
            bytes=file_bytes,
        )
        await self.file_repository.add_file(file_entity, workflow)

        # Publish submission.
        #

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
            patch_datacite_create_draft_doi(doi) as mock_datacite_create_draft_doi,
            patch_datacite_publish() as mock_datacite_publish,
            patch_pid_create_draft_doi(doi) as mock_pid_create_draft_doi,
            patch_pid_publish() as mock_pid_publish,
            # Rems
            patch_rems_create_resource() as mock_rems_create_resource,
            patch_rems_create_catalogue_item() as mock_rems_create_catalogue_item,
        ):
            # Publish submission.
            response = await self.client.patch(f"{API_PREFIX}/publish/{submission_id}")
            data = await response.json()
            assert response.status == 200
            assert data == {"submissionId": submission_id}

            mock_datacite_create_draft_doi.assert_awaited_once()
            mock_datacite_publish.assert_awaited_once()
            mock_pid_create_draft_doi.assert_not_awaited()
            mock_pid_publish.assert_not_awaited()

            # Assert Beacon.
            # TODO(improve): BP beacon service not implement

            # Assert Rems.
            mock_rems_create_resource.assert_awaited_once_with(rems.organizationId, rems.licenses, doi)
            mock_rems_create_catalogue_item.assert_awaited_once_with(
                rems.organizationId, rems.workflowId, 1, dataset_title, RemsServiceHandler().get_discovery_url(doi)
            )

            # Assert registrations.
            response = await self.client.get(f"{API_PREFIX}/submissions/{submission_id}/registrations")
            data = await response.json()
            assert response.status == 200
            registration = Registration.model_validate(data)
            # Check DOI
            assert registration.doi == doi
            # Check that metax ID does not exist
            assert registration.metaxId is None
            # Check REMS
            assert registration.remsResourceId is not None
            assert registration.remsCatalogueId is not None
            assert registration.remsUrl is not None
