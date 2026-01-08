"""NeIC SDA Admin service."""

from typing import Any, cast

from aiohttp import web
from yarl import URL

from ..conf.admin import admin_config
from ..helpers.logger import LOG
from .service_handler import ServiceHandler


class AdminServiceHandler(ServiceHandler):
    """NeIC SDA Admin service."""

    def __init__(self) -> None:
        """NeIC SDA Admin service."""

        self._config = admin_config()

        super().__init__(
            service_name="admin",
            base_url=URL(self._config.ADMIN_URL),
            healthcheck_url=URL(self._config.ADMIN_URL) / "ready",
        )

    @staticmethod
    def get_admin_auth_headers(req: web.Request) -> dict[str, str]:
        """Get authentication headers for Admin API service.

        :param req: HTTP request
        """
        try:
            admin_auth_header = {"Authorization": req.headers["X-Authorization"]}
            return admin_auth_header
        except KeyError as e:
            LOG.exception("Missing Authorization header")
            raise web.HTTPUnauthorized(reason="User is not authorized") from e

    async def ingest_file(self, req: web.Request, data: dict[str, str]) -> None:
        """Start the ingestion of a file.

        :param req: HTTP request
        :param data: Dict with request data including 'user' and 'filepath'
        :raises: HTTPInternalServerError if the file ingestion fails
        """
        admin_auth_headers = self.get_admin_auth_headers(req)
        ingestion_data = {"user": data["user"], "filepath": data["filepath"]}
        await self._request(method="POST", path="/file/ingest", json_data=ingestion_data, headers=admin_auth_headers)
        LOG.info("File in submission %s with path %r is being ingested", data["submissionId"], data["filepath"])

    async def get_user_files(self, req: web.Request, username: str) -> list[dict[str, Any]]:
        """Return information on all the user's files in inbox.

        :param req: HTTP request
        :param username: Username of the user whose files are retrieved
        :raises: HTTPInternalServerError if the file ingestion fails
        """
        admin_auth_headers = self.get_admin_auth_headers(req)
        user_files = await self._request(method="GET", path=f"/users/{username}/files", headers=admin_auth_headers)
        LOG.info("Fetched files from inbox for user %s", username)
        return cast(list[dict[str, Any]], user_files)

    async def post_accession_id(self, req: web.Request, data: dict[str, str]) -> None:
        """Assign accession ID to a file.

        :param req: HTTP request
        :param data: Dict with request data including 'user', 'filepath' and 'accessionId'
        :raises: HTTPInternalServerError if the file ingestion fails
        :raises: HTTPBadRequest if file does not belong to user
        """
        admin_auth_headers = self.get_admin_auth_headers(req)
        accession_data = {"user": data["user"], "filepath": data["filepath"], "accession_id": data["accessionId"]}
        await self._request(method="POST", path="/file/accession", json_data=accession_data, headers=admin_auth_headers)
        LOG.info("Accession ID %s assigned to file %s", accession_data["accession_id"], accession_data["filepath"])

    async def create_dataset(self, req: web.Request, data: dict[str, str | list[str]]) -> None:
        """Create dataset for user.

        :param req: HTTP request
        :param data: Dict with request data including 'user', 'fileIds' and 'datasetId'
        :raises: HTTPInternalServerError if the file accession IDs are not valid
        """
        admin_auth_headers = self.get_admin_auth_headers(req)
        dataset_data = {"user": data["user"], "accession_ids": data["fileIds"], "dataset_id": data["datasetId"]}
        await self._request(method="POST", path="/dataset/create", json_data=dataset_data, headers=admin_auth_headers)
        LOG.info("Dataset %s has been created", dataset_data["dataset_id"])

    async def release_dataset(self, req: web.Request, dataset: str) -> None:
        """Create dataset for user.

        :param req: HTTP request
        :param dataset: Dataset accession ID
        :raises: HTTPNotFound if the dataset is not found
        :raises: HTTPBadRequest if the dataset does not have status 'registered'
        """
        admin_auth_headers = self.get_admin_auth_headers(req)
        await self._request(method="POST", path=f"/dataset/release/{dataset}", headers=admin_auth_headers)
        LOG.info("Dataset %s has been released", dataset)
