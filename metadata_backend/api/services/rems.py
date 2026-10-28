"""REMS Services."""

from abc import ABC, abstractmethod

from ...services.rems_service import RemsServiceHandler
from ..exceptions import UserException
from ..models.rems import (
    License,
    Organization,
    OrganizationsMap,
    RemsCatalogueItem,
    RemsLicense,
    RemsLicenseLocalization,
    RemsOrganization,
    RemsResource,
    RemsWorkflow,
    Workflow,
)
from ..models.submission import Rems, Submission


class RemsLicenseProvider(ABC):
    """Creates a REMS license for the submission, if no licence has been provided."""

    @abstractmethod
    async def get_license(self, submission: Submission) -> dict[str, RemsLicenseLocalization] | None:
        """
        Get the REMS license of a submission.

        :param submission: The submission.
        :return: The REMS license localisations for each language, keyed by
            language code, or None if no license can be created.
        """


async def generate_rems_license_id(
    rems_service: RemsServiceHandler,
    license_provider: RemsLicenseProvider | None,
    submission: Submission,
    organization_id: str,
) -> int | None:
    """Generate a REMS license for the submission using its license provider.

    An identical license is reused if REMS already has one, so generating the same license
    twice gives the same id rather than a duplicate.

    :param rems_service: The REMS service.
    :param license_provider: The license provider, or None if the deployment has none.
    :param submission: The submission.
    :param organization_id: The REMS organization id owning the license.
    :returns: The REMS license id, or None if the deployment has no license provider or
        the provider gives no license.
    """

    if license_provider is None:
        return None

    localizations = await license_provider.get_license(submission)
    if localizations is None:
        return None

    return await rems_service.get_or_create_license(organization_id, localizations)


async def resolve_rems_license_ids(
    rems_service: RemsServiceHandler,
    license_provider: RemsLicenseProvider | None,
    rems: Rems,
    submission: Submission,
    organization_id: str,
) -> list[int]:
    """Resolve the REMS license ids to be associated with the REMS resource.

    License ids can be given in the submission. These license ids are
    validated. If license ids are not given in the submission then
    a license can be generated using a license provider.

    :param rems_service: The REMS service.
    :param license_provider: The license provider, or None if the deployment has none.
    :param rems: The rems metadata.
    :param submission: The submission.
    :param organization_id: The REMS organization id owning the licenses.
    :raises UserException: if a given license id is unknown to REMS.
    :returns: The REMS license ids, empty if the submission has no license.
    """

    if rems.licenses:
        # Validate given license ids.
        for license_id in rems.licenses:
            await rems_service.get_license(organization_id, license_id)
        return list(rems.licenses)

    # Generate license.
    license_id = await generate_rems_license_id(rems_service, license_provider, submission, organization_id)
    return [license_id] if license_id is not None else []


async def find_rems_resource(rems_service: RemsServiceHandler, resid: str, organization_id: str) -> RemsResource | None:
    """Find the active REMS resource with the given external id, to reuse it.

    The resource's licenses are not checked against the submission's licenses. This is by design:
    the REMS API cannot modify the licenses of an existing resource, so a reused resource keeps
    the licenses it was created with.

    :param rems_service: The REMS service.
    :param resid: The external resource id.
    :param organization_id: The REMS organization id the resource must belong to.
    :raises UserException: if there are several resources, or the resource belongs to another organization.
    :returns: The REMS resource, or None if there is none.
    """

    resources = [resource for resource in await rems_service.get_resources(resid) if resource.resid == resid]
    if not resources:
        return None
    if len(resources) > 1:
        ids = ", ".join(str(resource.id) for resource in resources)
        raise UserException(f"REMS has several resources '{resid}': {ids}.")
    resource = resources[0]
    if resource.organization.id != organization_id:
        raise UserException(
            f"REMS resource '{resid}' belongs to REMS organization '{resource.organization.id}', "
            f"not '{organization_id}'."
        )
    return resource


async def find_rems_catalogue_item(
    rems_service: RemsServiceHandler, resid: str, organization_id: str, workflow_id: int, resource_id: int | None
) -> RemsCatalogueItem | None:
    """Find the active REMS catalogue item of the resource with the given external id, to reuse it.

    Only the resource, organization and workflow are checked, not the title or discovery URL.

    :param rems_service: The REMS service.
    :param resid: The external resource id.
    :param organization_id: The REMS organization id the catalogue item must belong to.
    :param workflow_id: The REMS workflow id the catalogue item must have.
    :param resource_id: The REMS id of the active resource the catalogue item must belong to, or None if
        there is no active resource yet.
    :raises UserException: if there are several catalogue items, or the catalogue item belongs to
        another resource or organization, or has another workflow.
    :returns: The REMS catalogue item, or None if there is none.
    """

    items = [item for item in await rems_service.get_catalogue_items(resid) if item.resid == resid and not item.expired]
    if not items:
        return None
    if len(items) > 1:
        ids = ", ".join(str(item.id) for item in items)
        raise UserException(f"REMS resource '{resid}' has several catalogue items: {ids}.")
    item = items[0]
    if item.resource_id != resource_id:
        active = f"the active REMS resource '{resource_id}'" if resource_id is not None else "an active REMS resource"
        raise UserException(
            f"REMS catalogue item '{item.id}' belongs to REMS resource '{item.resource_id}', not to {active}."
        )
    if item.organization.id != organization_id:
        raise UserException(
            f"REMS catalogue item '{item.id}' belongs to REMS organization '{item.organization.id}', "
            f"not '{organization_id}'."
        )
    if item.workflow_id is not None and item.workflow_id != workflow_id:
        raise UserException(
            f"REMS catalogue item '{item.id}' has REMS workflow '{item.workflow_id}', not '{workflow_id}'."
        )
    return item


class RemsOrganisationsService:
    """Service to convert REMS API workflows and licenses to SD Submit API organisations with workflows and licenses."""

    @staticmethod
    def _get_localized_organisation_name(rems_organisation: RemsOrganization, language: str) -> str | None:
        """
        Get localized organisation name.

        :param rems_organisation: REMS organisation.
        :param language: Preferred language code (e.g. "en").
        :return: Localized organisation name or empty string if not found.
        """

        name = rems_organisation.name.get(language)
        if not name:
            name = next(iter(rems_organisation.name.values()))
        if not name:
            name = ""
        return name

    @staticmethod
    def _get_license_localization(rems_license: RemsLicense, language: str) -> RemsLicenseLocalization | None:
        """
        Get license localization for a given language.

        Falls back to the first available localization if the requested language
        is not present.

        :param rems_license: REMS license containing localized metadata.
        :param language: Preferred language code (e.g. "en").
        :return: Matching license localization or None if unavailable.
        """

        localizations = rems_license.localizations
        localization = localizations.get(language)
        if not localization:
            localization = next(iter(localizations.values()))
        if localization:
            return localization
        return None

    @staticmethod
    def _get_localized_license_title(rems_license: RemsLicense, language: str) -> str | None:
        """
        Get localized license title.

        :param rems_license: REMS license.
        :param language: Preferred language code (e.g. "en").
        :return: Localized license title or empty string if not found.
        """

        localization = RemsOrganisationsService._get_license_localization(rems_license, language)
        if localization:
            return localization.title
        return ""

    @staticmethod
    def _get_localized_license_textcontext(rems_license: RemsLicense, language: str) -> str | None:
        """
        Get localized license text content.

        :param rems_license: REMS license.
        :param language: Preferred language code (e.g. "en").
        :return: Localized license text or empty string if not found.
        """

        localization = RemsOrganisationsService._get_license_localization(rems_license, language)
        if localization:
            return localization.textcontent
        return ""

    @staticmethod
    def _add_organization(
        organizations: OrganizationsMap,
        rems_organization: RemsOrganization,
        language: str,
        filter_organisation_id: str | None = None,
    ) -> Organization | None:
        """
        Add an organization to the organizations collection.

        :param organizations: Mapping of organization IDs to Organization models.
        :param rems_organization: REMS organization to add.
        :param language: Preferred language code (e.g. "en").
        :param filter_organisation_id: Optional organization ID filter.
        :return: The added or existing Organization, or None if filtered out.
        """

        if filter_organisation_id and rems_organization.id != filter_organisation_id:
            return None

        if rems_organization.id not in organizations:
            organizations[rems_organization.id] = Organization(
                id=rems_organization.id,
                name=RemsOrganisationsService._get_localized_organisation_name(rems_organization, language),
                workflows=[],
                licenses=[],
            )
        return organizations[rems_organization.id]

    @staticmethod
    def _add_license(
        organizations: OrganizationsMap,
        rems_license: RemsLicense,
        language: str,
        filter_organisation_id: str | None = None,
    ) -> None:
        """
        Add a license to its associated organization.

        :param organizations: Mapping of organization IDs to Organization models.
        :param rems_license: REMS license to add.
        :param language: Preferred language code (e.g. "en").
        :param filter_organisation_id: Optional organization ID filter.
        """

        rems_organization = rems_license.organization
        organisation = RemsOrganisationsService._add_organization(
            organizations, rems_organization, language, filter_organisation_id
        )
        if organisation is not None:
            organisation.licenses.append(
                License(
                    id=rems_license.id,
                    title=RemsOrganisationsService._get_localized_license_title(rems_license, language),
                    textcontent=RemsOrganisationsService._get_localized_license_textcontext(rems_license, language),
                )
            )

    @staticmethod
    def _add_workflow(
        organizations: OrganizationsMap,
        rems_workflow: RemsWorkflow,
        language: str,
        filter_organisation_id: str | None = None,
    ) -> None:
        """
        Add a workflow and its licenses to its associated organization.

        :param organizations: Mapping of organization IDs to Organization models.
        :param rems_workflow: REMS workflow to add.
        :param language: Preferred language code (e.g. "en").
        :param filter_organisation_id: Optional organization ID filter.
        """

        rems_organization = rems_workflow.organization
        organisation = RemsOrganisationsService._add_organization(
            organizations, rems_organization, language, filter_organisation_id
        )
        if organisation is not None:
            licenses = []
            if rems_workflow.workflow.licenses:
                licenses = [
                    License(
                        id=rems_license.id,
                        title=RemsOrganisationsService._get_localized_license_title(rems_license, language),
                        textcontent=RemsOrganisationsService._get_localized_license_textcontext(rems_license, language),
                    )
                    for rems_license in rems_workflow.workflow.licenses
                ]
            organisation.workflows.append(Workflow(id=rems_workflow.id, title=rems_workflow.title, licenses=licenses))

    @staticmethod
    async def get_organisations(
        workflows: list[RemsWorkflow],
        licenses: list[RemsLicense],
        language: str = "en",
        filter_organisation_id: str | None = None,
    ) -> OrganizationsMap:
        """
        Get organizations with their workflows and licenses.

        :param workflows: REMS workflow.
        :param licenses: REMS licenses.
        :param language: Preferred language code (e.g. "en").
        :param filter_organisation_id: Optional organization ID filter.
        :return: REMS organizations with their workflows and licenses.
        """

        organizations: OrganizationsMap = {}

        for licence in licenses:
            RemsOrganisationsService._add_license(organizations, licence, language, filter_organisation_id)

        for workflow in workflows:
            RemsOrganisationsService._add_workflow(organizations, workflow, language, filter_organisation_id)

        return organizations
