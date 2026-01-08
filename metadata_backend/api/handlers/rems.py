"""REMS API handler."""

from aiohttp import web

from ..json import to_json_dict
from ..models.rems import OrganizationsMap, RemsLicense, RemsWorkflow
from ..services.rems import RemsOrganisationsService
from .restapi import RESTAPIHandler


class RemsAPIHandler(RESTAPIHandler):
    """REMS API handler."""

    async def get_organisations(self, request: web.Request) -> web.Response:
        """Get organisations with workflows and licenses."""

        language = request.query.get("language", "en")
        organisation_id = request.query.get("organisation")

        workflows: list[RemsWorkflow] = await self._handlers.rems.get_workflows()
        licenses: list[RemsLicense] = await self._handlers.rems.get_licenses()

        organizations: OrganizationsMap = await RemsOrganisationsService.get_organisations(
            workflows, licenses, language, organisation_id
        )
        return web.json_response(data=[to_json_dict(o) for o in organizations.values()])
