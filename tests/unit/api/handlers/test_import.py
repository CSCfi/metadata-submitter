"""Tests for the import API handler."""

import io
from unittest.mock import AsyncMock, patch

import pytest

from metadata_backend.api.models.sda import DatasetFile, DatasetStatus
from metadata_backend.api.models.submission import SubmissionWorkflow
from metadata_backend.api.processors.xml.bigpicture import BP_DATASET_OBJECT_TYPE
from metadata_backend.api.services.accession import generate_bp_accession_prefix
from metadata_backend.conf.deployment import deployment_config
from metadata_backend.services.admin_service import AdminServiceHandler
from tests.unit.database.postgres.helpers import create_submission_entity
from tests.unit.patches.user import MOCK_USER_ID, patch_verify_authorization, patch_verify_user_project
from tests.utils import BP_ANNOTATION_1_FILE, BP_IMAGE_1_FILE, BP_IMAGE_2_FILE, bp_objects_with_dataset_id

# The root directory of the imported dataset in SDA.
_SDA_ROOT = "ROOT"


# The accession of the imported dataset.
_DATASET_ID = f"{generate_bp_accession_prefix(BP_DATASET_OBJECT_TYPE)}-abcdef-ghjkmn"


def _sda_files() -> list[DatasetFile]:
    """The data files and old metadata XMLs of the version 2.0 test files in SDA, without the landing page."""
    data_files = [BP_IMAGE_1_FILE, BP_IMAGE_2_FILE, BP_ANNOTATION_1_FILE]
    metadata_files = [
        f"METADATA/{name}.xml"
        for name in ("dataset", "policy", "image", "annotation", "observation", "observer", "sample", "staining")
    ]
    return [
        DatasetFile(id=f"file-{i}", accessionID=f"accession-{i}", path=f"{_SDA_ROOT}/{path}.c4gh")
        for i, path in enumerate([*data_files, *metadata_files])
    ]


def _multipart_xmls(dataset_id: str) -> list[tuple[str, tuple[str, io.BytesIO, str]]]:
    return [
        (o.filename, (o.filename, io.BytesIO(o.document.encode()), "application/xml"))
        for o in bp_objects_with_dataset_id(dataset_id)
    ]


@pytest.fixture
def import_users(monkeypatch):
    """Allow the mock user to import datasets."""
    monkeypatch.setenv("IMPORT_USERS", f'["{MOCK_USER_ID}"]')


@pytest.fixture
def sda_dataset(monkeypatch):
    """
    Make the test XMLs importable and publishable without using external services.

    Yields the accession of the mocked SDA dataset.
    """

    # The import checks the dataset in SDA with the SDA Admin API. The mocked dataset is released and has
    # exactly the data files and metadata XMLs that the test XMLs import.
    patch_status = patch.object(
        AdminServiceHandler, "get_dataset_status", AsyncMock(return_value=DatasetStatus.RELEASED)
    )
    patch_files = patch.object(AdminServiceHandler, "list_ingested_files", AsyncMock(return_value=_sda_files()))
    # The test XMLs have a clinical policy, so the import checks REMS, and publishing registers the dataset
    # with REMS and DataCite. ALLOW_REGISTRATION False disables both.
    monkeypatch.setenv("ALLOW_REGISTRATION", "false")
    with patch_status, patch_files:
        yield _DATASET_ID


def test_import_requires_allowed_user(nbis_client, monkeypatch):
    monkeypatch.delenv("IMPORT_USERS", raising=False)
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    with patch_verify_user_project, patch_verify_authorization:
        response = nbis_client.post(f"{api_prefix_v1}/import", files=_multipart_xmls(_DATASET_ID))
        assert response.status_code == 403
        assert "The user is not allowed to import datasets." in response.text
        response = nbis_client.delete(f"{api_prefix_v1}/import/{_DATASET_ID}")
        assert response.status_code == 403
        assert "The user is not allowed to import datasets." in response.text


def test_delete_import(nbis_client, import_users, sda_dataset):
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    dataset_id = sda_dataset

    with patch_verify_user_project, patch_verify_authorization:
        response = nbis_client.post(f"{api_prefix_v1}/import", files=_multipart_xmls(dataset_id))
        assert response.status_code == 200, response.text

        response = nbis_client.delete(f"{api_prefix_v1}/import/{dataset_id}")
        assert response.status_code == 204
        assert nbis_client.get(f"{api_prefix_v1}/submissions/{dataset_id}").status_code == 404


def test_import_not_served_by_csc(csc_client):
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    with patch_verify_user_project, patch_verify_authorization:
        response = csc_client.post(f"{api_prefix_v1}/import", files=_multipart_xmls(_DATASET_ID))
        assert response.status_code == 404
        response = csc_client.delete(f"{api_prefix_v1}/import/{_DATASET_ID}")
        assert response.status_code == 404


def test_import_and_publish(nbis_client, import_users, sda_dataset):
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    dataset_id = sda_dataset

    with patch_verify_user_project, patch_verify_authorization:
        response = nbis_client.post(f"{api_prefix_v1}/import", files=_multipart_xmls(dataset_id))
        assert response.status_code == 200, response.text
        submission = response.json()
        assert submission["submissionId"] == dataset_id
        assert submission["imported"] is True

        # The submit endpoints cannot change an imported submission.
        response = nbis_client.patch(f"{api_prefix_v1}/submit/{dataset_id}", files=_multipart_xmls(dataset_id))
        assert response.status_code == 400
        assert f"Submission '{dataset_id}' was imported. Use the {api_prefix_v1}/import endpoints" in response.text
        response = nbis_client.delete(f"{api_prefix_v1}/submit/{dataset_id}")
        assert response.status_code == 400
        assert f"Submission '{dataset_id}' was imported. Use the {api_prefix_v1}/import endpoints" in response.text

        with (
            patch(
                "metadata_backend.api.services.workflow.upload_bp_metadata_xmls", new_callable=AsyncMock
            ) as mock_upload_bp_metadata_xmls,
            # The inbox is not checked when an imported submission is published.
            patch(
                "metadata_backend.api.services.file.S3InboxSDAService.find_missing_files", new_callable=AsyncMock
            ) as mock_find_missing_files,
            patch(
                "metadata_backend.api.services.file.S3InboxSDAService.list_submission_inbox_files",
                new_callable=AsyncMock,
            ) as mock_list_submission_inbox_files,
            patch(
                "metadata_backend.api.services.file.S3InboxSDAService.find_orphaned_files", new_callable=AsyncMock
            ) as mock_find_orphaned_files,
        ):
            mock_list_submission_inbox_files.return_value = []
            mock_find_missing_files.return_value = []
            mock_find_orphaned_files.return_value = []

            response = nbis_client.patch(
                f"{api_prefix_v1}/publish/{dataset_id}", headers={"Authorization": "Bearer oidc-token"}
            )
            assert response.status_code == 200, response.text
            mock_upload_bp_metadata_xmls.assert_awaited_once()
            mock_find_missing_files.assert_not_awaited()
            mock_find_orphaned_files.assert_not_awaited()
            mock_list_submission_inbox_files.assert_not_awaited()


async def test_delete_import_not_imported(nbis_client, import_users, submission_repository):
    """Test that the import endpoint does not delete a submission created with the submit endpoints."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    submission_id = await submission_repository.add_submission(
        create_submission_entity(workflow=SubmissionWorkflow.BP, project_id=MOCK_USER_ID)
    )

    with patch_verify_user_project, patch_verify_authorization:
        response = nbis_client.delete(f"{api_prefix_v1}/import/{submission_id}")
        assert response.status_code == 400
        assert (
            f"Submission '{submission_id}' was not imported. Use the {api_prefix_v1}/submit endpoints" in response.text
        )
