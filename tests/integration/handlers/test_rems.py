"""Test REMS handler."""

import logging

from metadata_backend.api.models.rems import Organization
from metadata_backend.conf.deployment import deployment_config

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


async def test_rems(sd_client, secret_env):
    """Test REMS handler."""

    async with sd_client.get(f"{deployment_config().API_PREFIX_V1}/rems?") as resp:
        result = await resp.json()
        organisations = [Organization.model_validate(o) for o in result]

        organisation = next(o for o in organisations if o.id == "nbn")
        assert organisation.name == "NBN"

        workflow = next(w for w in organisation.workflows if w.id == 1)
        assert workflow.title == "Default workflow"

        workflow_license = next(license for license in workflow.licenses if license.id == 7)
        assert workflow_license.title == "CC Attribution 4.0"
        assert workflow_license.textcontent == "https://creativecommons.org/licenses/by/4.0/legalcode"

        organisation_license = next(license for license in organisation.licenses if license.id == 7)
        assert organisation_license == workflow_license
