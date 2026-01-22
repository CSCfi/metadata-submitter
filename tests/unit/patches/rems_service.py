# Rems service handler patches.

from unittest.mock import AsyncMock, MagicMock, patch

from metadata_backend.api.exceptions import UserException
from metadata_backend.api.models.rems import (
    RemsCatalogueItem,
    RemsCatalogueItemLocalization,
    RemsLicense,
    RemsLicenseLocalization,
    RemsOrganization,
    RemsResource,
    RemsWorkflow,
    RemsWorkflowDetails,
)
from metadata_backend.services.rems_service import RemsServiceHandler

MOCK_REMS_DEFAULT_ORGANISATION_ID = "1"
MOCK_REMS_DEFAULT_WORKFLOW_ID = 1
MOCK_REMS_DEFAULT_LICENSE_ID = 1


def _mock_rems_create_organisation(organisation_id: str) -> RemsOrganization:
    return RemsOrganization(
        id=organisation_id,
        name={"fi": "test_name", "en": "test_name", "sv": "test_name"},
        short_name={
            "fi": "test_short_name",
            "en": "test_short_name",
            "sv": "test_short_name",
        },
    )


def _mock_rems_create_license(organisation_id: str, license_id: int) -> RemsLicense:
    return RemsLicense(
        id=license_id,
        licensetype="link",
        localizations={
            "en": RemsLicenseLocalization(title="test_title", textcontent="test_content"),
            "fi": RemsLicenseLocalization(title="test_title", textcontent="test_content"),
            "sv": RemsLicenseLocalization(title="test_title", textcontent="test_content"),
        },
        organization=_mock_rems_create_organisation(organisation_id),
        archived=False,
        enabled=True,
    )


def _mock_rems_create_workflow(organisation_id: str, workflow_id: int, license_id: int) -> RemsWorkflow:
    return RemsWorkflow(
        id=workflow_id,
        title="test",
        workflow=RemsWorkflowDetails(
            type="workflow/default", licenses=[_mock_rems_create_license(organisation_id, license_id)]
        ),
        organization=_mock_rems_create_organisation(organisation_id),
        archived=False,
        enabled=True,
    )


_mock_rems_organisations = {
    MOCK_REMS_DEFAULT_ORGANISATION_ID: _mock_rems_create_organisation(organisation_id=MOCK_REMS_DEFAULT_ORGANISATION_ID)
}
_mock_rems_workflows = {
    MOCK_REMS_DEFAULT_WORKFLOW_ID: _mock_rems_create_workflow(
        organisation_id=MOCK_REMS_DEFAULT_ORGANISATION_ID,
        workflow_id=MOCK_REMS_DEFAULT_WORKFLOW_ID,
        license_id=MOCK_REMS_DEFAULT_LICENSE_ID,
    )
}
_mock_rems_licenses = {
    MOCK_REMS_DEFAULT_LICENSE_ID: _mock_rems_create_license(
        organisation_id=MOCK_REMS_DEFAULT_ORGANISATION_ID, license_id=MOCK_REMS_DEFAULT_LICENSE_ID
    )
}
_mock_rems_resources: dict[int, RemsResource] = {}  # key: resource id
_mock_rems_catalogue_items: dict[int, RemsCatalogueItem] = {}  # key: catalogue id

mock_rems_resource_id = 1
mock_rems_catalogue_id = 1


async def _mock_rems_get_workflow(organization_id: str | None, workflow_id: int) -> RemsWorkflow:
    workflow = _mock_rems_workflows[workflow_id]
    if organization_id and organization_id != workflow.organization.id:
        raise UserException(f"REMS workflow '{workflow_id}' does not belong to REMS organization '{organization_id}'")
    return workflow


async def _mock_rems_get_license(organization_id: str | None, license_id: int) -> RemsLicense:
    license = _mock_rems_licenses[license_id]
    if organization_id and organization_id != license.organization.id:
        raise UserException(f"REMS license '{license_id}' does not belong to REMS organization '{organization_id}'")
    return license


async def _mock_rems_get_resources(doi: str | None = None) -> list[RemsResource]:
    if doi:
        return [resource for resource in _mock_rems_resources.values() if resource.doi == doi]
    return list(_mock_rems_resources.values())


async def _mock_rems_create_resource(
    organization_id: str | None, workflow_id: int, license_ids: list[int] | None, doi: str
) -> int:
    _mock_rems_resources[mock_rems_resource_id] = RemsResource(
        id=mock_rems_resource_id,
        resid=doi,
        organization=_mock_rems_organisations[organization_id],
        licenses=[_mock_rems_licenses[license_id] for license_id in license_ids if license_id in _mock_rems_licenses],
        archived=False,
        enabled=False,
    )
    return mock_rems_resource_id


async def _mock_rems_create_catalogue_item(
    organization_id: str, workflow_id: int, resource_id: int, title: str, discovery_url: str
) -> int:
    resource = _mock_rems_resources[resource_id]
    localization = RemsCatalogueItemLocalization(title=title, discovery_url=discovery_url)
    _mock_rems_catalogue_items[mock_rems_catalogue_id] = RemsCatalogueItem(
        id=mock_rems_catalogue_id,
        resource_id=resource.id,
        resid=resource.resid,
        organization=_mock_rems_organisations[organization_id],
        localizations={
            "en": localization,
            "fi": localization,
            "sv": localization,
        },
        archived=False,
        enabled=False,
        expired=False,
    )
    return mock_rems_catalogue_id


def patch_rems_get_discovery_url(url_prefix: str = "test_discovery"):
    return patch.object(
        RemsServiceHandler, "get_discovery_url", new=MagicMock(side_effect=lambda id: f"{url_prefix}/{id}")
    )


def patch_rems_get_application_url(url_prefix: str = "test_application"):
    return patch.object(
        RemsServiceHandler,
        "get_application_url",
        new=MagicMock(side_effect=lambda catalogue_id: f"{url_prefix}/application?items={catalogue_id}"),
    )


def patch_rems_get_workflows(workflows: list[RemsWorkflow] | None = None):
    if workflows is None:
        workflows = list(_mock_rems_workflows.values())
    return patch.object(RemsServiceHandler, "get_workflows", new=AsyncMock(return_value=workflows))


def patch_rems_get_workflow():
    return patch.object(RemsServiceHandler, "get_workflow", new=AsyncMock(side_effect=_mock_rems_get_workflow))


def patch_rems_get_licenses(licenses: list[RemsLicense] | None = None):
    if licenses is None:
        licenses = list(_mock_rems_licenses.values())
    return patch.object(RemsServiceHandler, "get_licenses", new=AsyncMock(return_value=licenses))


def patch_rems_get_license():
    return patch.object(RemsServiceHandler, "get_license", new=AsyncMock(side_effect=_mock_rems_get_license))


def patch_rems_get_resources():
    return patch.object(RemsServiceHandler, "get_resources", new=AsyncMock(side_effect=_mock_rems_get_resources))


def patch_rems_get_catalogue_item():
    return patch.object(
        RemsServiceHandler,
        "get_catalogue_item",
        new=AsyncMock(side_effect=lambda catalogue_id: _mock_rems_catalogue_items[catalogue_id]),
    )


def patch_rems_create_resource():
    return patch.object(RemsServiceHandler, "create_resource", new=AsyncMock(side_effect=_mock_rems_create_resource))


def patch_rems_create_catalogue_item():
    return patch.object(
        RemsServiceHandler, "create_catalogue_item", new=AsyncMock(side_effect=_mock_rems_create_catalogue_item)
    )


# Apply default Rems service handler patches.
patch_rems_get_discovery_url().start()
patch_rems_get_application_url().start()
patch_rems_get_workflows().start()
patch_rems_get_workflow().start()
patch_rems_get_licenses().start()
patch_rems_get_license().start()
patch_rems_get_resources().start()
patch_rems_get_catalogue_item().start()
patch_rems_create_resource().start()
patch_rems_create_catalogue_item().start()
