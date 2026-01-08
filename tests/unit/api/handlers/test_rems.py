"""Tests for REMS API handler."""

import logging

from metadata_backend.api.models.rems import Organization
from metadata_backend.conf.conf import API_PREFIX

from ...patches.rems_service import patch_rems_get_licenses, patch_rems_get_workflows
from ..services.test_rems import assert_organisation, create_workflow_and_license
from .common import HandlersTestCase

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class RemsAPIHandlerTestCase(HandlersTestCase):
    """Tests for REMS API handler."""

    async def test_rems(self):
        """Test /rems endpoint."""

        rems_workflows, rems_licenses = create_workflow_and_license()

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
            patch_rems_get_workflows(rems_workflows),
            patch_rems_get_licenses(rems_licenses),
        ):
            response = await self.client.get(f"{API_PREFIX}/rems")
            result = await response.json()
            assert response.status == 200

            organisations = [Organization.model_validate(o) for o in result]
            assert_organisation(organisations)
