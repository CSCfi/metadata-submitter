import random
import string
import uuid

import pytest

from metadata_backend.api.exceptions import UserException
from metadata_backend.api.models.rems import (
    RemsCatalogueItemLocalization,
    RemsLicense,
    RemsLicenseLocalization,
    RemsOrganization,
    RemsResource,
    RemsWorkflow,
    RemsWorkflowDetails,
)
from metadata_backend.conf.discovery import discovery_config
from metadata_backend.services.rems_service import REMS_LICENSE_TYPE_TEXT, RemsServiceHandler

# Test service: https://rems-test.2.rahtiapp.fi/swagger-ui/index.htm
# Test data: https://github.com/CSCfi/rems/blob/master/src/clj/rems/service/test_data.clj

ORGANISATION = RemsOrganization(
    id="nbn", name={"fi": "NBN", "en": "NBN", "sv": "NBN"}, short_name={"fi": "NBN", "en": "NBN", "sv": "NBN"}
)


def create_doi():
    suffix = "".join(random.choices(string.digits, k=9))
    return f"urn:nbn:fi:test-{suffix}"


async def test_get_licenses(secret_env):
    """Test REMS get licenses using test service and test data."""

    from metadata_backend.services.rems_service import RemsServiceHandler

    service = RemsServiceHandler()

    expected_license = RemsLicense(
        id="1",
        licensetype="link",
        localizations={
            "en": RemsLicenseLocalization(
                title="Demo license", textcontent="https://www.apache.org/licenses/LICENSE-2.0"
            ),
            "fi": RemsLicenseLocalization(
                title="Demolisenssi", textcontent="https://www.apache.org/licenses/LICENSE-2.0"
            ),
            "sv": RemsLicenseLocalization(
                title="Demolicens", textcontent="https://www.apache.org/licenses/LICENSE-2.0"
            ),
        },
        organization=RemsOrganization(
            id="nbn", name={"fi": "NBN", "en": "NBN", "sv": "NBN"}, short_name={"fi": "NBN", "en": "NBN", "sv": "NBN"}
        ),
    )

    licenses = await service.get_licenses()
    assert expected_license in licenses


async def test_get_or_create_license(secret_env):
    # REMS licenses cannot be deleted, only archived. THis test creates one new license.

    service = RemsServiceHandler()

    localizations = {
        "en": RemsLicenseLocalization(title=f"test_{uuid.uuid4()}", textcontent="test license text content"),
    }

    # No license matches the localizations, so one is created.
    license_id = await service.get_or_create_license(ORGANISATION.id, localizations)
    assert license_id is not None

    # The created license is found rather than a second one created.
    assert await service.get_or_create_license(ORGANISATION.id, localizations) == license_id

    # The created license is returned as it was given.
    rems_license = await service.get_license(ORGANISATION.id, license_id)
    assert rems_license.id == license_id
    assert rems_license.licensetype == REMS_LICENSE_TYPE_TEXT
    assert rems_license.localizations == localizations
    assert rems_license.organization == ORGANISATION

    # The created license is one of the active licenses.
    assert rems_license in await service.get_licenses()

    # The created license belongs to no other organisation.
    with pytest.raises(UserException, match="does not belong to REMS organization"):
        await service.get_license("other_organisation", license_id)


async def test_get_license_unknown_license(secret_env):
    service = RemsServiceHandler()
    with pytest.raises(UserException, match="Unknown REMS license"):
        await service.get_license(ORGANISATION.id, 999999999)


async def test_get_workflows(secret_env):
    """Test REMS get workflows using test service and test data."""

    from metadata_backend.services.rems_service import RemsServiceHandler

    service = RemsServiceHandler()

    expected_workflow = RemsWorkflow(
        id=1,
        archived=False,
        enabled=True,
        title="Default workflow",
        workflow=RemsWorkflowDetails(
            type="workflow/default",
            licenses=[
                RemsLicense(
                    id=7,
                    licensetype="link",
                    localizations={
                        "en": RemsLicenseLocalization(
                            title="CC Attribution 4.0",
                            textcontent="https://creativecommons.org/licenses/by/4.0/legalcode",
                            attachment_id=None,
                        ),
                        "fi": RemsLicenseLocalization(
                            title="CC Nimeä 4.0",
                            textcontent="https://creativecommons.org/licenses/by/4.0/legalcode.fi",
                            attachment_id=None,
                        ),
                        "sv": RemsLicenseLocalization(
                            title="CC Erkännande 4.0",
                            textcontent="https://creativecommons.org/licenses/by/4.0/legalcode.sv",
                            attachment_id=None,
                        ),
                    },
                    organization=RemsOrganization(
                        id="nbn",
                        name={"fi": "NBN", "en": "NBN", "sv": "NBN"},
                        short_name={"fi": "NBN", "en": "NBN", "sv": "NBN"},
                    ),
                ),
                RemsLicense(
                    id=8,
                    licensetype="text",
                    localizations={
                        "en": RemsLicenseLocalization(
                            title="General Terms of Use",
                            textcontent="License text in English. License text in English. License text in English. "
                            "License text in English. License text in English. License text in English. "
                            "License text in English. License text in English. License text in English. "
                            "License text in English. ",
                            attachment_id=None,
                        ),
                        "fi": RemsLicenseLocalization(
                            title="Yleiset käyttöehdot",
                            textcontent="Suomenkielinen lisenssiteksti. Suomenkielinen lisenssiteksti. Suomenkielinen "
                            "lisenssiteksti. Suomenkielinen lisenssiteksti. Suomenkielinen lisenssiteksti. "
                            "Suomenkielinen lisenssiteksti. Suomenkielinen lisenssiteksti. Suomenkielinen "
                            "lisenssiteksti. Suomenkielinen lisenssiteksti. Suomenkielinen lisenssiteksti. ",
                            attachment_id=None,
                        ),
                        "sv": RemsLicenseLocalization(
                            title="Allmänna villkor",
                            textcontent="Licens på svenska. Licens på svenska. Licens på svenska. Licens på svenska. "
                            "Licens på svenska. Licens på svenska. Licens på svenska. Licens på svenska. "
                            "Licens på svenska. Licens på svenska. ",
                            attachment_id=None,
                        ),
                    },
                    organization=RemsOrganization(
                        id="nbn",
                        name={"fi": "NBN", "en": "NBN", "sv": "NBN"},
                        short_name={"fi": "NBN", "en": "NBN", "sv": "NBN"},
                    ),
                ),
            ],
        ),
        organization=RemsOrganization(
            id="nbn", name={"fi": "NBN", "en": "NBN", "sv": "NBN"}, short_name={"fi": "NBN", "en": "NBN", "sv": "NBN"}
        ),
    )

    workflows = await service.get_workflows()
    assert expected_workflow in workflows


async def test_get_resources(secret_env):
    """Test REMS get resources using test service and test data."""

    from metadata_backend.services.rems_service import RemsServiceHandler

    service = RemsServiceHandler()

    expected_resource = RemsResource(
        id=1,
        resid="urn:nbn:fi:lb-201403262",
        organization=RemsOrganization(
            id="nbn", name={"fi": "NBN", "en": "NBN", "sv": "NBN"}, short_name={"fi": "NBN", "en": "NBN", "sv": "NBN"}
        ),
        licenses=[],
        archived=False,
        enabled=True,
    )

    resources = await service.get_resources()
    assert expected_resource in resources

    resources = await service.get_resources(doi="urn:nbn:fi:lb-201403262")
    assert [expected_resource] == resources


async def test_create_resource(secret_env):
    """Test REMS create resource using test service and test data."""

    from metadata_backend.services.rems_service import RemsServiceHandler

    service = RemsServiceHandler()

    doi = create_doi()
    resource_id = await service.create_resource(organization_id="nbn", license_ids=[1], resid=doi)
    assert resource_id is not None

    resources = await service.get_resources(doi=doi)
    assert len(resources) == 1
    assert resources[0].id == resource_id
    assert resources[0].resid == doi


async def test_create_catalogue_item(secret_env):
    """Test REMS create catalogue item using test service and test data."""

    from metadata_backend.services.rems_service import RemsServiceHandler

    handler = RemsServiceHandler()

    doi = create_doi()
    resource_id = await handler.create_resource(organization_id="nbn", license_ids=[1], resid=doi)

    title = f"test_{uuid.uuid4()}"
    discovery_url = discovery_config().DISCOVERY_URL.format(id=doi)
    item_id = await handler.create_catalogue_item(
        organization_id="nbn", workflow_id=1, resource_id=resource_id, title=title, discovery_url=discovery_url
    )

    item = await handler.get_catalogue_item(item_id)
    assert item.resource_id == resource_id
    assert item.resid == doi
    assert item.organization == ORGANISATION
    assert item.localizations == {"en": RemsCatalogueItemLocalization(title=title, discovery_url=discovery_url)}
    assert item.enabled
    assert not item.archived
    assert not item.expired
