from typing import Tuple

from metadata_backend.api.models.rems import (
    Organizations,
    RemsLicense,
    RemsLicenseLocalization,
    RemsOrganization,
    RemsWorkflow,
    RemsWorkflowDetails,
)
from metadata_backend.api.services.rems import RemsOrganisationsService

ORGANISATION_ID = "Organisation id"
ORGANISATION_NAME = "Organisation name"
LICENSE_ID = 1
LICENSE_TITLE = "License title"
LICENSE_TEXT_CONTENT = "License text content"
LICENCE_ATTACHEMENT_ID = "License attachment id"
WORKFLOW_ID = 1
WORKFLOW_TITLE = "Workflow title"


def create_workflow_and_license() -> Tuple[list[RemsWorkflow], list[RemsLicense]]:
    rems_organization = RemsOrganization(
        id=ORGANISATION_ID, name={"en": ORGANISATION_NAME}, short_name={"en": "Test Short Name"}
    )
    rems_license_localization = RemsLicenseLocalization(
        title=LICENSE_TITLE,
        textcontent=LICENSE_TEXT_CONTENT,
    )
    rems_license = RemsLicense(
        id=LICENSE_ID,
        licensetype="Test Licence Type",
        localizations={"en": rems_license_localization},
        organization=rems_organization,
        archived=False,
        enabled=True,
    )
    rems_workflow = RemsWorkflow(
        id=WORKFLOW_ID,
        title=WORKFLOW_TITLE,
        organization=rems_organization,
        workflow=RemsWorkflowDetails(
            type="default",
            licenses=[rems_license],
        ),
        archived=False,
        enabled=True,
    )

    return [rems_workflow], [rems_license]


def assert_organisation(organisations: Organizations) -> None:
    assert len(organisations) == 1

    # Check organisation.
    organisation = organisations[0]
    assert organisation is not None
    assert organisation.id == ORGANISATION_ID
    assert organisation.name == ORGANISATION_NAME

    # Check licenses.
    assert len(organisation.licenses) == 1
    license = organisation.licenses[0]
    assert license.id == LICENSE_ID
    assert license.title == LICENSE_TITLE
    assert license.textcontent == LICENSE_TEXT_CONTENT

    # Check workflows.
    assert len(organisation.workflows) == 1
    workflow = organisation.workflows[0]
    assert workflow.id == WORKFLOW_ID
    assert workflow.title == WORKFLOW_TITLE
    assert len(workflow.licenses) == 1
    assert workflow.licenses[0] == license


async def test_get_organizations():
    rems_workflows, rems_licenses = create_workflow_and_license()
    organisations = await RemsOrganisationsService.get_organisations(rems_workflows, rems_licenses)
    assert_organisation(list(organisations.values()))
