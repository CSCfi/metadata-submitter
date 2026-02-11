"""REMS API handler."""

from typing import Annotated

from fastapi import Query

from ..models.rems import Organization, OrganizationsMap, RemsLicense, RemsWorkflow
from ..services.rems import RemsOrganisationsService
from .restapi import RESTAPIHandler

RemsLanguageQueryParam = Annotated[str, Query(description="REMS language code (e.g. 'en', 'fi', 'sv')")]
RemsOrganisationIdFilterQueryParam = Annotated[
    str | None, Query(alias="organisation", description="REMS organisation ID")
]


class RemsAPIHandler(RESTAPIHandler):
    """REMS API handler."""

    async def get_organisations(
        self,
        language: RemsLanguageQueryParam = "en",
        organisation_id: RemsOrganisationIdFilterQueryParam = None,
    ) -> list[Organization]:
        """Get REMS organisations with workflows and licenses."""

        workflows: list[RemsWorkflow] = await self._handlers.rems.get_workflows()
        licenses: list[RemsLicense] = await self._handlers.rems.get_licenses()

        organizations: OrganizationsMap = await RemsOrganisationsService.get_organisations(
            workflows, licenses, language, organisation_id
        )
        return list(organizations.values())
