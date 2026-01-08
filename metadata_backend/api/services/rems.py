"""REMS Services."""

from ..models.rems import (
    License,
    Organization,
    OrganizationsMap,
    RemsLicense,
    RemsLicenseLocalization,
    RemsOrganization,
    RemsWorkflow,
    Workflow,
)


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
