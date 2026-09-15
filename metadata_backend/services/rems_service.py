"""REMS service."""

import hashlib
import json
import math
from typing import Any
from urllib.parse import quote

from cachetools import TTLCache
from starlette import status
from yarl import URL

from ..api.exceptions import ServiceHandlerSystemException, UserException
from ..api.models.rems import (
    RemsCatalogueItem,
    RemsLicense,
    RemsLicenseLocalization,
    RemsResource,
    RemsWorkflow,
)
from ..conf.rems import rems_config
from .service_handler import ServiceHandler

REMS_LICENSE_TYPE_TEXT = "text"

# How long the REMS licenses are remembered. REMS has no license search by content, so
# every active license is listed and matched against. All requests share the cache.
REMS_LICENSE_CACHE_TTL = 7 * 24 * 60 * 60.0


def license_cache_key(organization_id: str, localizations: dict[str, RemsLicenseLocalization]) -> str:
    """The key identifying a text license by its organization and localizations.

    :param organization_id: The REMS organization id.
    :param localizations: The license localizations.
    :returns: The key, equal for two licenses with the same organization and localizations.
    """

    identity = json.dumps(
        {
            "organization": organization_id,
            "localizations": {
                language: [localization.title, localization.textcontent]
                for language, localization in localizations.items()
            },
        },
        # Sorted, to guarantee localizations order.
        sort_keys=True,
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


class RemsServiceHandler(ServiceHandler):
    """REMS service."""

    def __init__(self) -> None:
        """REMS service."""

        config = rems_config()

        super().__init__(
            service_name="rems",
            base_url=URL(config.REMS_URL) / "api",
            http_client_headers={
                "x-rems-api-key": config.REMS_KEY,
                "x-rems-user-id": config.REMS_USER,
                "accept": "application/json",
            },
            healthcheck_url=URL(config.REMS_URL) / "api" / "health",
        )

        # License id cache.
        self._license_cache = self.new_license_cache()

    @staticmethod
    def new_license_cache() -> TTLCache[str, int]:
        """A new cache of license ids, unbounded and expiring after the cache window."""

        return TTLCache(maxsize=math.inf, ttl=REMS_LICENSE_CACHE_TTL)

    @staticmethod
    def get_application_url(catalogue_id: str) -> str:
        """
        Get REMS data access application URL.

        :param catalogue_id: The REMS catalogue item ID
        :returns: The REMS data access application URL.
        """

        return f"{rems_config().REMS_URL.rstrip('/')}/application?items={quote(catalogue_id)}"

    async def get_workflows(self) -> list[RemsWorkflow]:
        """
        Get active REMS workflows.

        :returns: The list of active REMS workflows.
        """

        response: dict[str, Any] = await self._request(
            method="GET", path="/workflows", params={"disabled": "false", "archived": "false"}
        )
        return [RemsWorkflow.model_validate(workflow) for workflow in response]

    async def get_workflow(self, organization_id: str | None, workflow_id: int) -> RemsWorkflow:
        """
        Get active REMS workflow.

        :param organization_id: The REMS organisation id.
        :param workflow_id: The REMS workflow id.
        :returns: The active REMS workflow.
        """

        try:
            response: dict[str, Any] = await self._request(
                method="GET",
                path=f"/workflows/{workflow_id}",
                params={"disabled": "false", "archived": "false"},
            )
        except ServiceHandlerSystemException as ex:
            if ex.service_status_code == status.HTTP_404_NOT_FOUND:
                raise UserException(f"Unknown REMS workflow '{workflow_id}'") from ex
            raise ex

        workflow = RemsWorkflow.model_validate(response)
        if organization_id and workflow.organization.id != organization_id:
            raise UserException(
                f"REMS workflow '{workflow_id}' does not belong to REMS organization '{organization_id}'"
            )

        return workflow

    async def get_licenses(self) -> list[RemsLicense]:
        """
        Get active REMS licenses.

        :returns: The list of active REMS licenses.
        """

        # Example of REMS API response.
        #
        # [
        #   {
        #     "id": 0,
        #     "licensetype": "text",
        #     "organization": {
        #       "organization/id": "string",
        #       ...
        #     },
        #     "enabled": true,
        #     "archived": true,
        #     "localizations": {
        #       "en": {
        #         "title": "General Terms of Use",
        #         "textcontent": "License text in English."
        #       },
        #       "fi": {
        #         "title": "Yleiset käyttöehdot",
        #         "textcontent": "Suomenkielinen lisenssiteksti.",
        #         "attachment-id": 0
        #       }
        #     }
        #   }
        # ]
        response: dict[str, Any] = await self._request(
            method="GET", path="/licenses", params={"disabled": "false", "archived": "false"}
        )
        return [RemsLicense.model_validate(rems_license) for rems_license in response]

    async def get_license(self, organization_id: str | None, license_id: int) -> RemsLicense:
        """
        Get active REMS license.

        :param organization_id: The REMS organisation id.
        :param license_id: The REMS license id.
        :returns: The active REMS license.
        """

        try:
            response: dict[str, Any] = await self._request(
                method="GET",
                path=f"/licenses/{license_id}",
                params={"disabled": "false", "archived": "false"},
            )
        except ServiceHandlerSystemException as ex:
            if ex.service_status_code == status.HTTP_404_NOT_FOUND:
                raise UserException(f"Unknown REMS license '{license_id}'") from ex
            raise ex
        rems_license = RemsLicense.model_validate(response)
        if organization_id and rems_license.organization.id != organization_id:
            raise UserException(f"REMS license '{license_id}' does not belong to REMS organization '{organization_id}'")
        return rems_license

    async def create_license(self, organization_id: str, localizations: dict[str, RemsLicenseLocalization]) -> int:
        """Create a REMS text license.

        :param organization_id: The REMS organization id.
        :param localizations: The license title and text content of each language, keyed
            by language code.
        :returns: The REMS license id.
        """

        # Example of REMS API request.
        #
        # {
        #   "licensetype": "text",
        #   "organization": {
        #     "organization/id": "string"
        #   },
        #   "localizations": {
        #     "en": {
        #       "title": "English title",
        #       "textcontent": "English content"
        #     },
        #     "fi": {
        #       "title": "Finnish title",
        #       "textcontent": "Finnish content"
        #     }
        #   }
        # }
        data = {
            "licensetype": REMS_LICENSE_TYPE_TEXT,
            "organization": {"organization/id": organization_id},
            "localizations": {
                language: {
                    "title": localization.title,
                    "textcontent": localization.textcontent,
                }
                for language, localization in localizations.items()
            },
        }

        response: dict[str, Any] = await self._request(method="POST", path="/licenses/create", json_data=data)
        return int(response["id"])

    async def get_or_create_license(
        self, organization_id: str, localizations: dict[str, RemsLicenseLocalization]
    ) -> int:
        """Get a matching REMS text license, or create it if none exists.

        A license matches when it belongs to the same organization and has exactly the same
        localizations, including localisation language, title, and text content.

        A license that is not found in the cache is searched in REMS before it is created.
        A license created here is cached, so asking for it again costs nothing.

        :param organization_id: The REMS organization id.
        :param localizations: The license localizations.
        :returns: The REMS license id.
        """

        cache_key = license_cache_key(organization_id, localizations)

        license_id = self._license_cache.get(cache_key)
        if license_id is None:
            # Check if the license exists in REMS.
            await self._refresh_licenses()
            license_id = self._license_cache.get(cache_key)

        if license_id is None:
            license_id = await self.create_license(organization_id, localizations)
            self._license_cache[cache_key] = license_id

        return license_id

    async def _refresh_licenses(self) -> None:
        """Retrieve all licenses from REMS and cache them."""

        for rems_license in await self.get_licenses():
            if rems_license.licensetype != REMS_LICENSE_TYPE_TEXT:
                continue

            cache_key = license_cache_key(rems_license.organization.id, rems_license.localizations)
            self._license_cache[cache_key] = rems_license.id

    async def get_resources(self, doi: str | None = None) -> list[RemsResource]:
        """
        Get active REMS resources.

        :param doi: The REMS resource DOI.
        :returns: The list of active REMS resources.
        """

        params = {"disabled": "false", "archived": "false"}
        if doi is not None:
            params["resid"] = doi
        response: dict[str, Any] = await self._request(method="GET", path="/resources", params=params)
        return [RemsResource.model_validate(resource) for resource in response]

    async def get_catalogue_item(self, catalogue_id: int) -> RemsCatalogueItem:
        """
        Get REMS catalogue item.

        :param catalogue_id: The REMS catalogue item id.
        :returns: The REMS catalogue item.
        """

        response: dict[str, Any] = await self._request(method="GET", path=f"/catalogue-items/{catalogue_id}")
        return RemsCatalogueItem.model_validate(response)

    async def create_resource(self, organization_id: str, license_ids: list[int] | None, resid: str) -> int:
        """Create a REMS resource.

        :param organization_id: The REMS organization id.
        :param license_ids: The REMS license ids.
        :returns: The REMS resource id.
        :param resid: The external resource id e.g. a DOI.
        """

        data = {
            "resid": resid,
            "organization": {"organization/id": organization_id},
            "licenses": license_ids or [],
        }

        response: dict[str, Any] = await self._request(method="POST", path="/resources/create", json_data=data)
        return int(response["id"])

    async def create_catalogue_item(
        self, organization_id: str, workflow_id: int, resource_id: int, title: str, discovery_url: str
    ) -> int:
        """Create a REMS catalogue item.

        :param resource_id: The REMS resource id.
        :param workflow_id: The REMS workflow id.
        :param organization_id: The REMS organization id.
        :param title: The REMS catalogue item title.
        :param discovery_url: The REMS catalogue item discovery url.
        :returns: The REMS catalogue item id.
        """

        data = {
            "resid": resource_id,
            "wfid": workflow_id,
            "organization": {"organization/id": organization_id},
            "localizations": {
                "en": {
                    "title": title,
                    "infourl": discovery_url,
                }
            },
        }
        created: dict[str, Any] = await self._request(method="POST", path="/catalogue-items/create", json_data=data)
        return int(created["id"])
