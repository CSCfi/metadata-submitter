"""REMS service."""

import json
from urllib.parse import quote

from yarl import URL

from ..api.exceptions import UserException
from ..api.models.rems import RemsCatalogueItem, RemsLicense, RemsResource, RemsWorkflow
from ..conf.rems import rems_config
from .service_handler import ServiceClientError, ServiceHandler


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

    @staticmethod
    def get_discovery_url(id: str) -> str:
        """
        Get REMS data discovery URL.

        :param id: The ID.
        :returns: The REMS data discovery URL.
        """

        return f"{rems_config().REMS_DISCOVERY_URL.rstrip('/')}/{id}"

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

        response = await self._request(
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
            response = await self._request(
                method="GET", path=f"/workflows/{workflow_id}", params={"disabled": "false", "archived": "false"}
            )
        except ServiceClientError as ex:
            if ex.status_code == 404:
                raise UserException(f"Unknown REMS workflow '{workflow_id}''")
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

        response = await self._request(
            method="GET", path="/licenses", params={"disabled": "false", "archived": "false"}
        )
        print(json.dumps(response))
        return [RemsLicense.model_validate(license) for license in response]

    async def get_license(self, organization_id: str | None, license_id: int) -> RemsWorkflow:
        """
        Get active REMS license.

        :param organization_id: The REMS organisation id.
        :param license_id: The REMS license id.
        :returns: The active REMS license.
        """

        try:
            response = await self._request(
                method="GET", path=f"/licenses/{license_id}", params={"disabled": "false", "archived": "false"}
            )
        except ServiceClientError as ex:
            if ex.status_code == 404:
                raise UserException(f"Unknown REMS license '{license_id}''")
            raise ex
        license = RemsWorkflow.model_validate(response)
        if organization_id and license.organization.id != organization_id:
            raise UserException(f"REMS license '{license_id}' does not belong to REMS organization '{organization_id}'")
        return license

    async def get_resources(self, doi: str | None = None) -> list[RemsResource]:
        """
        Get active REMS resources.

        :param doi: The REMS resource DOI.
        :returns: The list of active REMS resources.
        """

        params = {"disabled": "false", "archived": "false"}
        if doi is not None:
            params["resid"] = doi
        response = await self._request(method="GET", path="/resources", params=params)
        return [RemsResource.model_validate(resource) for resource in response]

    async def get_catalogue_item(self, catalogue_id: int) -> RemsCatalogueItem:
        """
        Get REMS catalogue item.

        :param catalogue_id: The REMS catalogue item id.
        :returns: The REMS catalogue item.
        """

        response = await self._request(method="GET", path=f"/catalogue-items/{catalogue_id}")
        return RemsCatalogueItem.model_validate(response)

    async def create_resource(
        self, organization_id: str | None, workflow_id: int, license_ids: list[int] | None, doi: str
    ) -> int:
        """Create a REMS resource.

        :param organization_id: The REMS organization id.
        :param workflow_id: The REMS workflow id.
        :param license_ids: The REMS license ids.
        :returns: The REMS resource id.
        :param doi: The dataset DOI.
        """

        # Check that the workflow exists.
        workflow = await self.get_workflow(organization_id, workflow_id)

        data = {
            "resid": doi,
            "organization": {"organization/id": workflow.organization.id},
            "licenses": license_ids or [],
        }
        response = await self._request(method="POST", path="/resources/create", json_data=data)
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
        created = await self._request(method="POST", path="/catalogue-items/create", json_data=data)
        return int(created["id"])
