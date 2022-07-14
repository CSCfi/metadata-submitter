"""Integrate with REMS service.

This integration allows pushing of datasets to REMS, so that researchers can apply for access to research datasets.
https://github.com/CSCfi/rems


Terminology translation
REMS                metadata-submitter
workflow    ->  	DAC
license     ->  	policy
resource    ->  	dataset

"""
from typing import Dict, List

from aiohttp import web
from yarl import URL

from .service_handler import ServiceHandler
from ..conf.conf import rems_config, REMS_ENABLED
from ..helpers.logger import LOG


class RemsServiceHandler(ServiceHandler):
    """REMS dataset access integration."""

    service_name = "Rems"

    def __init__(self) -> None:
        """Get REMS credentials from config."""
        super().__init__(
            base_url=URL(rems_config["url"]) / "api",
            http_client_headers={
                "x-rems-api-key": rems_config["key"],
                "x-rems-user-id": rems_config["id"],
                "accept": "application/json",
            },
        )

    @property
    def enabled(self) -> bool:
        """Indicate whether service is enabled."""
        return REMS_ENABLED

    @staticmethod
    def application_url(catalogue_id: str) -> str:
        """Return URL for data access application."""
        return "{}/application?items={}".format(rems_config["url"], catalogue_id)

    async def get_workflows(self) -> List[Dict]:
        """Get all active workflows.

        Workflow in REMS = DAC in metadata-submitter
        """
        return await self._request(method="GET", path="/workflows", params={"disabled": "false", "archived": "false"})

    async def get_licenses(self) -> List[Dict]:
        """Get all active licenses.

        License in REMS = policy in metadata-submitter
        """
        return await self._request(method="GET", path="/licenses", params={"disabled": "false", "archived": "false"})

    async def create_resource(self, doi: str, organization_id: str, licenses: List[int]) -> int:
        """Create a REMS resource for a dataset.

        :param doi: DOI id of the dataset
        :param organization_id: REMS organization/id
        :param licenses: List of REMS license ids
        :returns: id of the created resource
        """
        resource = {"resid": doi, "organization": {"organization/id": organization_id}, "licenses": licenses}
        LOG.debug(f"Creating new resource '{resource}'")
        created = await self._request(method="POST", path="/resources/create", json_data=resource)
        return int(created["id"])

    async def create_catalogue_item(
        self, resource_id: int, workflow_id: int, organization_id: str, localizations: Dict[str, Dict[str, str]]
    ) -> str:
        """Create a REMS resource for a dataset.

        :param resource_id: id of the REMS resource
        :param workflow_id: id of the REMS workflow/DAC
        :param organization_id: REMS organization/id
        :param localizations: Dictionary of languages and title of the dataset
        :returns: id of the created resource
        """
        catalogue = {
            "form": None,
            "resid": resource_id,
            "wfid": workflow_id,
            "organization": {"organization/id": organization_id},
            "localizations": localizations,
            "enabled": True,
            "archived": False,
        }
        LOG.debug(f"Creating new catalogue item '{catalogue}'")
        created = await self._request(method="POST", path="/catalogue-items/create", json_data=catalogue)
        return created["id"]

    async def item_ok(self, item_type: str, organization_id: str, _id: int) -> bool:
        """Check that item exists.

        :param item_type: 'workflow' or 'license'
        :param organization_id: REMS organization/id
        :param _id: REMS item id
        :raises HTTPError
        :returns: True or raises
        """
        LOG.debug(f"Checking that {item_type} '{_id}' is ok.")
        capitalized_item_type = item_type.capitalize()

        try:
            item = await self._request(method="GET", path=f"/{item_type}s/{_id}")
            if not item["enabled"]:
                raise self.make_exception(reason=f"{capitalized_item_type} '{_id}' is disabled", status=400)
            if item["archived"]:
                raise self.make_exception(reason=f"{capitalized_item_type} '{_id}' is archived", status=400)
            if item["organization"]["organization/id"] != organization_id:
                raise self.make_exception(
                    reason=f"{capitalized_item_type} '{_id}' doesn't belong to organization '{organization_id}'",
                    status=400,
                )
        except KeyError:
            raise self.make_exception(reason=f"{capitalized_item_type} '{_id}' has unexpected structure.", status=400)
        except web.HTTPNotFound:
            raise self.make_exception(reason=f"{capitalized_item_type} '{_id}' doesn't exist.", status=400)

        LOG.debug(f"{capitalized_item_type} '{_id}' is ok.")
        return True

    async def validate_workflow_licenses(self, organization_id: str, workflow_id: int, licenses: List[int]) -> bool:
        """Check that workflow and policies exist.

        :param organization_id: REMS organization/id
        :param workflow_id: REMS workflow id
        :param licenses: List of REMS license ids
        :raises HTTPError
        :returns: True
        """
        LOG.debug(
            f"Checking that workflow '{workflow_id}' and licenses '{licenses}' "
            f"belong to organization {organization_id}, and pass other checks."
        )
        if not isinstance(organization_id, str):
            raise self.make_exception(reason=f"Organization id '{organization_id}' must be a string.", status=400)
        if not isinstance(workflow_id, int):
            raise self.make_exception(reason=f"Workflow id '{workflow_id}' must be an integer.", status=400)
        if not isinstance(licenses, list):
            raise self.make_exception(reason=f"Licenses '{licenses}' must be a list of integers.", status=400)

        await self.item_ok("workflow", organization_id, workflow_id)

        for license_id in licenses:
            if not isinstance(license_id, int):
                raise self.make_exception(reason=f"Workflow id '{license_id}' must be an integer.", status=400)

            await self.item_ok("license", organization_id, license_id)
        LOG.debug("All ok.")
        return True
