"""Test API endpoints from PublishSubmissionAPIHandler."""

import os
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, call, patch

import pytest

from metadata_backend.api.json import to_json_dict
from metadata_backend.api.models.datacite import Subject
from metadata_backend.api.models.models import Registration
from metadata_backend.api.models.submission import Rems, SubmissionMetadata, SubmissionWorkflow
from metadata_backend.api.services.file import FileProviderService
from metadata_backend.api.services.publish import get_publish_config
from metadata_backend.conf.conf import API_PREFIX
from metadata_backend.database.postgres.models import FileEntity
from metadata_backend.database.postgres.repositories.file import FileRepository
from metadata_backend.database.postgres.repositories.object import ObjectRepository
from metadata_backend.database.postgres.repositories.submission import (
    SUB_FIELD_METADATA,
    SUB_FIELD_REMS,
    SubmissionRepository,
)
from metadata_backend.services.rems_service_handler import RemsServiceHandler
from tests.unit.database.postgres.helpers import create_object_entity, create_submission_entity

from .common import HandlersTestCase


class PublishSubmissionHandlerTestCase(HandlersTestCase):
    """Publishing API endpoint class test cases."""

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

        user_id = "mock-userid"

        submission_metadata = self.submission_metadata

        # REMS information.
        rems = Rems(workflowId=1, organizationId=f"organisation_{str(uuid.uuid4())}", licenses=[1, 2])

        # The submission contains no metadata objects.

        submission_title = f"title_{str(uuid.uuid4())}"
        submission_description = f"description_{str(uuid.uuid4())}"

        # The submission contains one file.
        file_path = f"path_{str(uuid.uuid4())}"
        file_bytes = 1024

        # Mock data.
        metax_url = "https://mock.com/"
        metax_id = f"metax_{str(uuid.uuid4())}"
        doi_part1 = f"doi_{str(uuid.uuid4())}"
        doi_part2 = f"doi_{str(uuid.uuid4())}"
        doi = f"{doi_part1}/{doi_part2}"
        rems_resource_id = 1
        rems_catalogue_id = f"catalogue_{str(uuid.uuid4())}"

        # Create submission and files to allow the submission to be published.

        # Create submission.
        workflow = SubmissionWorkflow.SD
        publish_config = get_publish_config(workflow)
        submission_entity = create_submission_entity(
            workflow=workflow,
            title=submission_title,
            description=submission_description,
            document={SUB_FIELD_METADATA: submission_metadata, SUB_FIELD_REMS: to_json_dict(rems)},
        )
        submission_id = await self.submission_repository.add_submission(submission_entity)

        # Create file.
        file_entity = FileEntity(submission_id=submission_entity.submission_id, path=file_path, bytes=file_bytes)
        await self.file_repository.add_file(file_entity, workflow)

        # Publish submission.
        #

        pid_cls = "metadata_backend.services.pid_ms_handler.PIDServiceHandler"
        datacite_cls = "metadata_backend.services.datacite_service_handler.DataciteServiceHandler"
        metax_cls = "metadata_backend.services.metax_service_handler.MetaxServiceHandler"
        rems_cls = "metadata_backend.services.rems_service_handler.RemsServiceHandler"
        file_provider_cls = "metadata_backend.api.services.file.FileProviderService"

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
            # File provider
            patch(f"{file_provider_cls}.list_files_in_bucket", new_callable=AsyncMock) as mock_file_provider,
            # Datacite (csc)
            patch(f"{pid_cls}.create_draft_doi_pid", new_callable=AsyncMock) as mock_pid_create_doi,
            patch(f"{pid_cls}.publish", new_callable=AsyncMock) as mock_pid_publish,
            # Datacite (datacite)
            patch(f"{datacite_cls}.create_draft_doi_datacite", new_callable=AsyncMock) as mock_datacite_create_doi,
            patch(f"{datacite_cls}.publish", new_callable=AsyncMock) as mock_datacite_publish,
            # Metax
            patch.dict(os.environ, {"METAX_DISCOVERY_URL": metax_url}),
            patch(f"{metax_cls}.post_dataset_as_draft", new_callable=AsyncMock) as mock_metax_create,
            patch(f"{metax_cls}.update_dataset_metadata", new_callable=AsyncMock) as mock_metax_update_dataset_metadata,
            patch(f"{metax_cls}.update_draft_dataset_description", new_callable=AsyncMock) as mock_metax_update_descr,
            patch(f"{metax_cls}.publish_dataset", new_callable=AsyncMock) as mock_metax_publish,
            # REMS
            patch(f"{rems_cls}.create_resource", new_callable=AsyncMock) as mock_rems_create_resource,
            patch(f"{rems_cls}.create_catalogue_item", new_callable=AsyncMock) as mock_rems_create_catalogue_item,
        ):
            # Mock file provider.
            mock_file_provider.return_value = FileProviderService.Files(
                [FileProviderService.File(path=file_path, bytes=file_bytes)]
            )
            # Mock Datacite.
            mock_pid_create_doi.return_value = doi
            mock_datacite_create_doi.return_value = doi
            # Mock Metax.
            mock_metax_create.return_value = metax_id
            # Mock Rems.
            mock_rems_create_resource.return_value = rems_resource_id
            mock_rems_create_catalogue_item.return_value = rems_catalogue_id

            # Publish submission.
            response = await self.client.patch(f"{API_PREFIX}/publish/{submission_entity.submission_id}")
            data = await response.json()
            assert response.status == 200
            assert data == {"submissionId": submission_id}

            # Assert Datacite.

            datacite_data = {
                "id": doi,
                "type": "dois",
                "data": {
                    "attributes": {
                        "publisher": {"name": "CSC - IT Center for Science"},
                        "publicationYear": datetime.now().year,
                        "event": "publish",
                        "schemaVersion": "https://schema.datacite.org/meta/kernel-4",
                        "doi": doi,
                        "prefix": doi_part1,
                        "suffix": doi_part2,
                        "types": {
                            "ris": "DATA",
                            "bibtex": "misc",
                            "citeproc": "dataset",
                            "schemaOrg": "Dataset",
                        },
                        "url": f"{metax_url}{metax_id}",
                        "identifiers": [{"identifierType": "DOI", "doi": doi}],
                        "titles": [{"lang": None, "title": submission_title, "titleType": None}],
                        "descriptions": [
                            {"lang": None, "description": submission_description, "descriptionType": "Other"}
                        ],
                        "creators": [
                            {
                                "name": "Creator, Test",
                                "nameType": "Personal",
                                "givenName": "Test",
                                "familyName": "Creator",
                                "affiliation": [
                                    {
                                        "name": "affiliation place",
                                        "schemeUri": "https://ror.org",
                                        "affiliationIdentifier": "https://ror.org/test1",
                                        "affiliationIdentifierScheme": "ROR",
                                    }
                                ],
                            }
                        ],
                        "resourceType": {"resourceTypeGeneral": "Dataset", "resourceType": "Dataset"},
                        "subjects": [
                            {
                                "subject": "999 - Other",
                                "subjectScheme": "Korkeakoulujen tutkimustiedonkeruussa käytettävä tieteenalaluokitus",
                                "schemeUri": "http://www.yso.fi/onto/okm-tieteenala/conceptscheme",
                                "valueUri": "http://www.yso.fi/onto/okm-tieteenala/ta999",
                                "classificationCode": "999",
                            }
                        ],
                    }
                },
            }

            assert not publish_config.use_datacite_service
            assert publish_config.use_pid_service

            mock_pid_create_doi.assert_awaited_once_with()
            mock_pid_publish.assert_awaited_once_with(datacite_data)

            # Assert Metax.
            mock_metax_create.assert_awaited_once_with(user_id, doi, submission_title, submission_description)

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

            mock_metax_update_dataset_metadata.assert_awaited_once_with(
                expected_submission_metadata,
                metax_id,
                file_bytes,
                related_dataset=None,
                related_study=None,
            )
            mock_metax_update_descr.assert_awaited_once_with(
                metax_id,
                f"{submission_description}\n\nSD Apply's Application link: {RemsServiceHandler.application_url(rems_catalogue_id)}",
            )

            mock_metax_publish.assert_awaited_once_with(metax_id, doi)

            # Assert Rems.
            mock_rems_create_resource.assert_awaited_once_with(
                doi=doi, organization_id=rems.organizationId, licenses=rems.licenses
            )
            mock_rems_create_catalogue_item.assert_awaited_once_with(
                resource_id=rems_resource_id,
                workflow_id=rems.workflowId,
                organization_id=rems.organizationId,
                localizations={"en": {"title": submission_title, "infourl": f"{metax_url}{metax_id}"}},
            )

    async def test_publish_submission_fega(self):
        """Test publishing of FEGA submission."""

        user_id = "mock-userid"

        submission_metadata = self.submission_metadata

        # RENS information.
        rems = Rems(workflowId=1, organizationId=f"organisation_{str(uuid.uuid4())}", licenses=[1, 2])

        # The submission contains one dataset metadata object.
        dataset_object_type = "dataset"
        dataset_title = f"title_{str(uuid.uuid4())}"
        dataset_description = f"description_{str(uuid.uuid4())}"

        # The submission contains one study metadata object.
        study_object_type = "study"
        study_title = f"title_{str(uuid.uuid4())}"
        study_description = f"description_{str(uuid.uuid4())}"

        # The submission contains one file.
        file_path = f"path_{str(uuid.uuid4())}"
        file_bytes = 1024

        # Mock data.
        metax_url = "https://mock.com/"
        metax_id = f"metax_{str(uuid.uuid4())}"
        doi_part1 = f"doi_{str(uuid.uuid4())}"
        doi_part2 = f"doi_{str(uuid.uuid4())}"
        doi = f"{doi_part1}/{doi_part2}"
        rems_resource_id = 1
        rems_catalogue_id = f"catalogue_{str(uuid.uuid4())}"

        # Create submission and files to allow the submission to be published.

        # Create submission.
        workflow = SubmissionWorkflow.FEGA
        publish_config = get_publish_config(workflow)
        submission_entity = create_submission_entity(
            workflow=workflow, document={SUB_FIELD_METADATA: submission_metadata, SUB_FIELD_REMS: to_json_dict(rems)}
        )
        submission_id = await self.submission_repository.add_submission(submission_entity)

        # Create metadata objects.

        # Dataset.
        dataset_entity = create_object_entity(
            project_id=submission_entity.project_id,
            submission_id=submission_entity.submission_id,
            object_type=dataset_object_type,
            document={"test": "test"},
            title=dataset_title,
            description=dataset_description,
        )
        await self.object_repository.add_object(dataset_entity, workflow)

        # DAC.
        dac_entity = create_object_entity(
            project_id=submission_entity.project_id,
            submission_id=submission_entity.submission_id,
            object_type="dac",
            document={},
        )
        await self.object_repository.add_object(dac_entity, workflow)

        # Policy.
        policy_entity = create_object_entity(
            project_id=submission_entity.project_id,
            submission_id=submission_entity.submission_id,
            object_type="policy",
            document={},
        )
        await self.object_repository.add_object(policy_entity, workflow)

        # Study.
        study_entity = create_object_entity(
            project_id=submission_entity.project_id,
            submission_id=submission_entity.submission_id,
            object_type=study_object_type,
            document={},
            title=study_title,
            description=study_description,
        )
        await self.object_repository.add_object(study_entity, workflow)

        # Create file.
        file_entity = FileEntity(
            submission_id=submission_entity.submission_id,
            object_id=dataset_entity.object_id,
            path=file_path,
            bytes=file_bytes,
        )
        await self.file_repository.add_file(file_entity, workflow)

        # Publish submission.
        #

        pid_cls = "metadata_backend.services.pid_ms_handler.PIDServiceHandler"
        datacite_cls = "metadata_backend.services.datacite_service_handler.DataciteServiceHandler"
        metax_cls = "metadata_backend.services.metax_service_handler.MetaxServiceHandler"
        rems_cls = "metadata_backend.services.rems_service_handler.RemsServiceHandler"

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
            # Datacite (csc)
            patch(f"{pid_cls}.create_draft_doi_pid", new_callable=AsyncMock) as mock_pid_create_doi,
            patch(f"{pid_cls}.publish", new_callable=AsyncMock) as mock_pid_publish,
            # Datacite (datacite)
            patch(f"{datacite_cls}.create_draft_doi_datacite", new_callable=AsyncMock) as mock_datacite_create_doi,
            patch(f"{datacite_cls}.publish", new_callable=AsyncMock) as mock_datacite_publish,
            # Metax
            patch.dict(os.environ, {"METAX_DISCOVERY_URL": metax_url}),
            patch(f"{metax_cls}.post_dataset_as_draft", new_callable=AsyncMock) as mock_metax_create,
            patch(f"{metax_cls}.update_dataset_metadata", new_callable=AsyncMock) as mock_metax_update_dataset_metadata,
            patch(f"{metax_cls}.update_draft_dataset_description", new_callable=AsyncMock) as mock_metax_update_descr,
            patch(f"{metax_cls}.publish_dataset", new_callable=AsyncMock) as mock_metax_publish,
            # REMS
            patch(f"{rems_cls}.create_resource", new_callable=AsyncMock) as mock_rems_create_resource,
            patch(f"{rems_cls}.create_catalogue_item", new_callable=AsyncMock) as mock_rems_create_catalogue_item,
        ):
            # Mock Datacite.
            mock_pid_create_doi.return_value = doi
            mock_datacite_create_doi.return_value = doi
            # Mock Metax.
            mock_metax_create.return_value = metax_id
            # Mock Rems.
            mock_rems_create_resource.return_value = rems_resource_id
            mock_rems_create_catalogue_item.return_value = rems_catalogue_id

            # Publish submission.
            response = await self.client.patch(f"{API_PREFIX}/publish/{submission_entity.submission_id}")
            data = await response.json()
            assert response.status == 200
            assert data == {"submissionId": submission_id}

            # Assert Datacite.

            dataset_datacite_data = {
                "id": doi,
                "type": "dois",
                "data": {
                    "attributes": {
                        "publisher": {"name": "CSC - IT Center for Science"},
                        "publicationYear": datetime.now().year,
                        "event": "publish",
                        "schemaVersion": "https://schema.datacite.org/meta/kernel-4",
                        "doi": doi,
                        "prefix": doi_part1,
                        "suffix": doi_part2,
                        "types": {
                            "ris": "DATA",
                            "bibtex": "misc",
                            "citeproc": "dataset",
                            "schemaOrg": "Dataset",
                        },
                        "url": f"{metax_url}{metax_id}",
                        "identifiers": [{"identifierType": "DOI", "doi": doi}],
                        "titles": [{"lang": None, "title": dataset_title, "titleType": None}],
                        "descriptions": [
                            {"lang": None, "description": dataset_description, "descriptionType": "Other"}
                        ],
                        "creators": [
                            {
                                "name": "Creator, Test",
                                "nameType": "Personal",
                                "givenName": "Test",
                                "familyName": "Creator",
                                "affiliation": [
                                    {
                                        "name": "affiliation place",
                                        "schemeUri": "https://ror.org",
                                        "affiliationIdentifier": "https://ror.org/test1",
                                        "affiliationIdentifierScheme": "ROR",
                                    }
                                ],
                            }
                        ],
                        "resourceType": {"resourceTypeGeneral": "Dataset", "resourceType": "Dataset"},
                        "subjects": [{"subject": "999 - Other"}],
                        "relatedIdentifiers": [
                            {
                                "relationType": "IsDescribedBy",
                                "relatedIdentifier": doi,
                                "resourceTypeGeneral": "Collection",
                                "relatedIdentifierType": "DOI",
                            }
                        ],
                    }
                },
            }

            study_datacite_data = {
                "id": doi,
                "type": "dois",
                "data": {
                    "attributes": {
                        "publisher": {"name": "CSC - IT Center for Science"},
                        "publicationYear": datetime.now().year,
                        "event": "publish",
                        "schemaVersion": "https://schema.datacite.org/meta/kernel-4",
                        "doi": doi,
                        "prefix": doi_part1,
                        "suffix": doi_part2,
                        "types": {
                            "bibtex": "misc",
                            "citeproc": "collection",
                            "schemaOrg": "Collection",
                        },
                        "url": f"{metax_url}{metax_id}",
                        "identifiers": [{"identifierType": "DOI", "doi": doi}],
                        "titles": [{"lang": None, "title": study_title, "titleType": None}],
                        "descriptions": [{"lang": None, "description": study_description, "descriptionType": "Other"}],
                        "creators": [
                            {
                                "name": "Creator, Test",
                                "nameType": "Personal",
                                "givenName": "Test",
                                "familyName": "Creator",
                                "affiliation": [
                                    {
                                        "name": "affiliation place",
                                        "schemeUri": "https://ror.org",
                                        "affiliationIdentifier": "https://ror.org/test1",
                                        "affiliationIdentifierScheme": "ROR",
                                    }
                                ],
                            }
                        ],
                        "resourceType": {"resourceTypeGeneral": "Collection", "resourceType": "Study"},
                        "subjects": [{"subject": "999 - Other"}],
                        "relatedIdentifiers": [
                            {
                                "relationType": "Describes",
                                "relatedIdentifier": doi,
                                "resourceTypeGeneral": "Dataset",
                                "relatedIdentifierType": "DOI",
                            }
                        ],
                    }
                },
            }

            assert not publish_config.use_datacite_service
            assert publish_config.use_pid_service

            assert mock_pid_create_doi.await_count == 2
            assert mock_pid_publish.await_count == 2
            assert call(dataset_datacite_data) in mock_pid_publish.await_args_list
            assert call(study_datacite_data) in mock_pid_publish.await_args_list

            # Assert Metax.
            assert mock_metax_create.await_count == 2
            assert call(user_id, doi, dataset_title, dataset_description) in mock_metax_create.await_args_list
            assert call(user_id, doi, study_title, study_description) in mock_metax_create.await_args_list
            assert mock_metax_update_dataset_metadata.await_count == 2

            expected_submission_metadata = SubmissionMetadata.model_validate(submission_metadata)

            # Dataset.
            assert (
                call(
                    expected_submission_metadata,
                    metax_id,
                    file_bytes,
                    related_dataset=Registration(
                        submissionId=submission_id,
                        objectId=dataset_entity.object_id,
                        objectType=dataset_object_type,
                        title=dataset_title,
                        description=dataset_description,
                        doi=doi,
                        metaxId=metax_id,
                        remsUrl=f"http://mockrems:8003/application?items={rems_catalogue_id}",
                        remsResourceId=str(rems_resource_id),
                        remsCatalogueId=rems_catalogue_id,
                    ),
                    related_study=None,
                )
                in mock_metax_update_dataset_metadata.await_args_list
            )

            # Study.
            assert (
                call(
                    expected_submission_metadata,
                    metax_id,
                    file_bytes,
                    related_dataset=None,
                    related_study=Registration(
                        submissionId=submission_id,
                        objectId=study_entity.object_id,
                        objectType=study_object_type,
                        title=study_title,
                        description=study_description,
                        doi=doi,
                        metaxId=metax_id,
                    ),
                )
                in mock_metax_update_dataset_metadata.await_args_list
            )

            mock_metax_update_descr.assert_awaited_once_with(
                metax_id,
                f"{dataset_description}\n\nSD Apply's Application link: {RemsServiceHandler.application_url(rems_catalogue_id)}",
            )

            assert mock_metax_publish.await_count == 2
            assert call(metax_id, doi) in mock_metax_publish.await_args_list

            # Assert Rems.
            mock_rems_create_resource.assert_awaited_once_with(
                doi=doi, organization_id=rems.organizationId, licenses=rems.licenses
            )
            mock_rems_create_catalogue_item.assert_awaited_once_with(
                resource_id=rems_resource_id,
                workflow_id=rems.workflowId,
                organization_id=rems.organizationId,
                localizations={"en": {"title": dataset_title, "infourl": f"{metax_url}{metax_id}"}},
            )

    async def test_publish_submission_bp(self):
        """Test publishing of BP submission."""

        submission_metadata = self.submission_metadata

        # RENS information.
        rems = Rems(workflowId=1, organizationId=f"organisation_{str(uuid.uuid4())}", licenses=[1, 2])

        # The submission contains one dataset metadata object.
        dataset_object_type = "dataset"
        dataset_title = f"title_{str(uuid.uuid4())}"
        dataset_description = f"description_{str(uuid.uuid4())}"

        # The submission contains one file.
        file_path = f"path_{str(uuid.uuid4())}"
        file_bytes = 1024

        # Mock data.
        beacon_url = "https://mock.com/"
        doi_part1 = f"doi_{str(uuid.uuid4())}"
        doi_part2 = f"doi_{str(uuid.uuid4())}"
        doi = f"{doi_part1}/{doi_part2}"
        rems_resource_id = 1
        rems_catalogue_id = f"catalogue_{str(uuid.uuid4())}"

        # Create submission and files to allow the submission to be published.

        # Create submission.
        workflow = SubmissionWorkflow.BP
        publish_config = get_publish_config(workflow)
        submission_entity = create_submission_entity(
            workflow=workflow, document={SUB_FIELD_METADATA: submission_metadata, SUB_FIELD_REMS: to_json_dict(rems)}
        )
        submission_id = await self.submission_repository.add_submission(submission_entity)

        # Create metadata object.
        object_entity = create_object_entity(
            project_id=submission_entity.project_id,
            submission_id=submission_entity.submission_id,
            object_type=dataset_object_type,
            document={},
            title=dataset_title,
            description=dataset_description,
        )
        await self.object_repository.add_object(object_entity, workflow)

        # Create file.
        file_entity = FileEntity(
            submission_id=submission_entity.submission_id,
            object_id=object_entity.object_id,
            path=file_path,
            bytes=file_bytes,
        )
        await self.file_repository.add_file(file_entity, workflow)

        # Publish submission.
        #

        pid_cls = "metadata_backend.services.pid_ms_handler.PIDServiceHandler"
        datacite_cls = "metadata_backend.services.datacite_service_handler.DataciteServiceHandler"
        rems_cls = "metadata_backend.services.rems_service_handler.RemsServiceHandler"

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
            # Datacite (csc)
            patch(f"{pid_cls}.create_draft_doi_pid", new_callable=AsyncMock) as mock_pid_create_doi,
            patch(f"{pid_cls}.publish", new_callable=AsyncMock) as mock_pid_publish,
            # Datacite (datacite)
            patch(f"{datacite_cls}.create_draft_doi_datacite", new_callable=AsyncMock) as mock_datacite_create_doi,
            patch(f"{datacite_cls}.publish", new_callable=AsyncMock) as mock_datacite_publish,
            # Metax
            patch.dict(os.environ, {"BEACON_DISCOVERY_URL": beacon_url}),
            # REMS
            patch(f"{rems_cls}.create_resource", new_callable=AsyncMock) as mock_rems_create_resource,
            patch(f"{rems_cls}.create_catalogue_item", new_callable=AsyncMock) as mock_rems_create_catalogue_item,
        ):
            # Mock Datacite.
            mock_pid_create_doi.return_value = doi
            mock_datacite_create_doi.return_value = doi
            # Mock Rems.
            mock_rems_create_resource.return_value = rems_resource_id
            mock_rems_create_catalogue_item.return_value = rems_catalogue_id

            # Publish submission.
            response = await self.client.patch(f"{API_PREFIX}/publish/{submission_entity.submission_id}")
            data = await response.json()
            assert response.status == 200
            assert data == {"submissionId": submission_id}

            # Assert Datacite.

            expected_datacite_request = {
                "id": doi,
                "type": "dois",
                "data": {
                    "attributes": {
                        "publisher": {"name": "CSC - IT Center for Science"},
                        "publicationYear": datetime.now().year,
                        "event": "publish",
                        "schemaVersion": "https://schema.datacite.org/meta/kernel-4",
                        "doi": doi,
                        "prefix": doi_part1,
                        "suffix": doi_part2,
                        "types": {
                            "ris": "DATA",
                            "bibtex": "misc",
                            "citeproc": "dataset",
                            "schemaOrg": "Dataset",
                        },
                        "url": f"{beacon_url}{doi}",
                        "identifiers": [{"identifierType": "DOI", "doi": doi}],
                        "titles": [{"lang": None, "title": dataset_title, "titleType": None}],
                        "descriptions": [
                            {"lang": None, "description": dataset_description, "descriptionType": "Other"}
                        ],
                        "creators": [
                            {
                                "name": "Creator, Test",
                                "nameType": "Personal",
                                "givenName": "Test",
                                "familyName": "Creator",
                                "affiliation": [
                                    {
                                        "name": "affiliation place",
                                        "schemeUri": "https://ror.org",
                                        "affiliationIdentifier": "https://ror.org/test1",
                                        "affiliationIdentifierScheme": "ROR",
                                    }
                                ],
                            }
                        ],
                        "resourceType": {"resourceTypeGeneral": "Dataset", "resourceType": "Dataset"},
                        "subjects": [
                            {
                                "subject": "999 - Other",
                            }
                        ],
                    }
                },
            }

            assert publish_config.use_datacite_service
            assert not publish_config.use_pid_service

            mock_datacite_create_doi.assert_awaited_once_with(dataset_object_type)
            mock_datacite_publish.assert_awaited_once_with(expected_datacite_request)

            # Assert Beacon.
            # TODO(improve): BP beacon service not implement

            # Assert Rems.
            mock_rems_create_resource.assert_awaited_once_with(
                doi=doi, organization_id=rems.organizationId, licenses=rems.licenses
            )
            mock_rems_create_catalogue_item.assert_awaited_once_with(
                resource_id=rems_resource_id,
                workflow_id=rems.workflowId,
                organization_id=rems.organizationId,
                localizations={"en": {"title": dataset_title, "infourl": f"{beacon_url}{doi}"}},
            )
