"""Tests for REMS API handler."""

import logging

from metadata_backend.api.models.rems import Organization
from metadata_backend.conf.conf import API_PREFIX
from tests.unit.patches.user import patch_verify_authorization, patch_verify_user_project

from ...patches.rems_service import patch_rems_get_licenses, patch_rems_get_workflows
from ..services.test_rems import assert_organisation, create_workflow_and_license

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


async def test_rems(csc_client):
    """Test /rems endpoint."""

    rems_workflows, rems_licenses = create_workflow_and_license()

    with (
        patch_verify_user_project,
        patch_verify_authorization,
        patch_rems_get_workflows(rems_workflows),
        patch_rems_get_licenses(rems_licenses),
    ):
        response = csc_client.get(f"{API_PREFIX}/rems")
        result = response.json()
        assert response.status_code == 200

        organisations = [Organization.model_validate(o) for o in result]
        assert_organisation(organisations)
