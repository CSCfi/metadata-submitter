"""Get and process REMS data for the frontend."""
from typing import Any, TypedDict

from aiohttp import web

from ...api.handlers.restapi import RESTAPIIntegrationHandler


class Organization(TypedDict):
    """Type for organization."""

    id: str
    name: str
    workflows: list[dict[str, str]]
    licenses: list[dict[str, str]]


class RemsAPIHandler(RESTAPIIntegrationHandler):
    """API Handler for REMS.

    Frontend can't access REMS directly.
    """

    @staticmethod
    def _get_localized(language: str, _dict: dict[str, Any], fallback_language: str = "en") -> str | dict[str, Any]:
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
            lang_dict: str | dict[str, Any] = _dict[language]
            return lang_dict
        if fallback_language in _dict:
            lang_dict = _dict[fallback_language]
            return lang_dict

        # return first element
        lang_dict = next(iter(_dict.values()))
        return lang_dict

    async def get_workflows_licenses_from_rems(self, request: web.Request) -> web.Response:
        """Get workflows and Policies for frontend."""
        language = request.query.get("language", "en").split("_")[0]
        workflows = await self.rems_handler.get_workflows()
        licenses = await self.rems_handler.get_licenses()

        organizations: dict[str, Organization] = {}

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

        for lic in licenses:
            title = self._get_localized(language, lic["localizations"])
            org_name = self._get_localized(language, lic["organization"]["organization/name"])
            org_id = lic["organization"]["organization/id"]
            if org_id not in organizations:
                add_organization(str(org_id), str(org_name))
            organizations[org_id]["licenses"].append({"id": lic["id"], **title})

        return web.json_response(data=list(organizations.values()))


# : dict[str, dict[str, dict[str, Any] | Any] | Any]
