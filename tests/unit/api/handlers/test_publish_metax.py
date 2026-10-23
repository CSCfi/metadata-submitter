"""Tests for validating the Metax metadata when a submission is published."""

from unittest.mock import AsyncMock, patch

from metadata_backend.api.exceptions import UserException
from metadata_backend.api.json import to_json_dict
from metadata_backend.api.models.submission import Rems
from metadata_backend.conf.deployment import deployment_config
from metadata_backend.database.postgres.repositories.submission import SUB_FIELD_METADATA, SUB_FIELD_REMS
from metadata_backend.services.metax_service import MetaxServiceHandler
from tests.unit.database.postgres.helpers import create_submission_entity
from tests.unit.patches.user import patch_verify_authorization, patch_verify_user_project

from ...patches.pid_service import patch_pid_create_draft_doi
from ...patches.rems_service import MOCK_REMS_DEFAULT_LICENSE_ID, MOCK_REMS_DEFAULT_WORKFLOW_ID
from .common import SUBMISSION_METADATA


async def test_publish_submission_sd_invalid_metax_metadata(csc_client, submission_repository, registration_repository):
    """Test that metadata Metax does not accept fails the publish before the DOI is registered."""
    rems = Rems(workflowId=MOCK_REMS_DEFAULT_WORKFLOW_ID, licenses=[MOCK_REMS_DEFAULT_LICENSE_ID])
    submission_id = await submission_repository.add_submission(
        create_submission_entity(document={SUB_FIELD_METADATA: SUBMISSION_METADATA, SUB_FIELD_REMS: to_json_dict(rems)})
    )

    with (
        patch_verify_user_project,
        patch_verify_authorization,
        patch.object(
            MetaxServiceHandler,
            "validate_dataset_metadata",
            new=AsyncMock(side_effect=UserException("Affiliation is required for Creator.")),
        ),
        patch_pid_create_draft_doi("doi") as mock_pid_create_draft_doi,
    ):
        # The files are not needed to reach the registration.
        response = csc_client.patch(f"{deployment_config().API_PREFIX_V1}/publish/{submission_id}?no_files=true")

    assert response.status_code == 400
    assert response.json()["errors"] == ["Affiliation is required for Creator."]
    mock_pid_create_draft_doi.assert_not_awaited()
    assert await registration_repository.get_registration(submission_id) is None
