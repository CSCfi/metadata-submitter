"""Get and process REMS data for the frontend."""
from typing import Union, Dict, TypedDict, List

from aiohttp import web

from ...api.handlers.restapi import RESTAPIIntegrationHandler


class Organization(TypedDict):
    """Type for organization."""

    id: str
    name: str
    workflows: List[Dict[str, str]]
    licenses: List[Dict[str, str]]


class RemsAPIHandler(RESTAPIIntegrationHandler):
    """API Handler for REMS.

    Frontend can't access REMS directly.
    """

    @staticmethod
    def _get_localized(language: str, _dict: dict, fallback_language: str = "en") -> Union[str, dict]:
        """Get correct language string from dict.

        REMS provides certain properties as a dict with language, but no way to know which are available.

        """
        if len(_dict) == 0:
            return ""
        if not isinstance(_dict, dict):
            if isinstance(_dict, str):
                return _dict
            return ""
        if language in _dict:
            return _dict[language]
        elif fallback_language in _dict:
            return _dict[fallback_language]

        # return first element
        return next(iter(_dict.values()))

    async def get_workflows_licenses_from_rems(self, request: web.Request) -> web.Response:
        """Get workflows and Policies for frontend."""

        language = request.query.get("language", "en").split("_")[0]
        workflows = await self.rems_handler.get_workflows()
        licenses = await self.rems_handler.get_licenses()

        organizations: Dict[str, Organization] = {}

        def add_organization(organization_id: str, organization_name: str) -> None:
            organizations[organization_id] = {
                "id": organization_id,
                "name": organization_name,
                "workflows": [],
                "licenses": [],
            }

        for workflow in workflows:
            title = workflow["title"]
            org_name = self._get_localized(language, workflow["organization"]["organization/name"])
            org_id = workflow["organization"]["organization/id"]
            if org_id not in organizations:
                add_organization(str(org_id), str(org_name))
            organizations[org_id]["workflows"].append({"id": workflow["id"], "title": title})

        for license in licenses:
            title = self._get_localized(language, license["localizations"])
            org_name = self._get_localized(language, license["organization"]["organization/name"])
            org_id = license["organization"]["organization/id"]
            if org_id not in organizations:
                add_organization(str(org_id), str(org_name))
            organizations[org_id]["licenses"].append({"id": license["id"], **title})

        return web.json_response(data=list(organizations.values()))
