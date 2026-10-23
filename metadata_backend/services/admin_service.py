"""NeIC SDA Admin service."""

from typing import Any

from starlette import status
from yarl import URL

from ..api.exceptions import ServiceHandlerSystemException, SystemException
from ..api.models.sda import (
    CreateDatasetRequest,
    DatasetFile,
    DatasetFilesResponse,
    DatasetStatus,
    FileItem,
    GetDatasetResponse,
    IngestFileRequest,
    PostAccessionIdRequest,
    UserFilesResponse,
)
from ..conf.admin import admin_config
from ..helpers.logger import LOG
from .service_handler import ServiceHandler

# A page of the user files lists up to 1000 files, and the Admin API can take most of the default
# 10 second timeout to return one while it is busy ingesting.
USER_FILES_TIMEOUT = 30


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

    def get_admin_auth_headers(self) -> dict[str, str]:
        """Get authentication headers for Admin API service."""
        if self._config.ADMIN_TOKEN:
            return {"Authorization": f"Bearer {self._config.ADMIN_TOKEN}"}
        else:
            LOG.error("Admin API token is not configured.")
            raise SystemException("Service configuration error.")

    async def get_user_files(self, username: str, path_prefix: str = "") -> list[FileItem]:
        """Return information on all the user's files in inbox.

        The Admin API returns the files a page at a time, with an ``X-Next-Cursor`` header while more
        pages remain, so every page is fetched until the header is absent.

        :param username: Username of the user whose files are retrieved
        :param path_prefix: Only the files under this path prefix are returned. All the user's files are
            returned without one.
        :returns: List of file information
        """
        admin_auth_headers = self.get_admin_auth_headers()

        params: dict[str, Any] = {"path_prefix": path_prefix} if path_prefix else {}
        user_files: list[FileItem] = []
        seen_cursors: set[str] = set()
        while True:
            response = await self._send(
                method="GET",
                path=f"/users/{username}/files",
                params=params or None,
                timeout=USER_FILES_TIMEOUT,
                headers=admin_auth_headers,
            )
            user_files.extend(self._validate_response(UserFilesResponse, self._content(response)).root)

            cursor = response.headers.get("X-Next-Cursor")
            if not cursor:
                break
            # A cursor returned twice would page forever, and a partial list would hide files.
            if cursor in seen_cursors:
                LOG.error("Admin API returned pagination cursor %r twice for user %s", cursor, username)
                raise ServiceHandlerSystemException(self.service_name)
            seen_cursors.add(cursor)
            params = {**params, "cursor": cursor}

        LOG.debug("Fetched %d files from inbox for user %s", len(user_files), username)
        return user_files

    async def list_ingested_files(self, dataset_id: str) -> list[DatasetFile] | None:
        """Return all ingested files in a dataset.

        The Admin API returns the files a page at a time, with an ``X-Next-Cursor`` header while more
        pages remain. Every page is fetched until the header is absent.

        :param dataset_id: Dataset accession ID
        :returns: The files in the dataset, or ``None`` if the dataset does not exist.
        """
        admin_auth_headers = self.get_admin_auth_headers()

        params: dict[str, Any] = {}
        dataset_files: list[DatasetFile] = []
        seen_cursors: set[str] = set()
        while True:
            try:
                response = await self._send(
                    method="GET",
                    path=f"/dataset/{dataset_id}/files",
                    params=params or None,
                    timeout=USER_FILES_TIMEOUT,
                    headers=admin_auth_headers,
                )
            except ServiceHandlerSystemException as e:
                if e.service_status_code == status.HTTP_404_NOT_FOUND:
                    return None
                raise
            dataset_files.extend(self._validate_response(DatasetFilesResponse, self._content(response)).root)

            cursor = response.headers.get("X-Next-Cursor")
            if not cursor:
                break
            # A cursor returned twice would page forever, and a partial list would hide files.
            if cursor in seen_cursors:
                LOG.error("Admin API returned pagination cursor %r twice for dataset %s", cursor, dataset_id)
                raise ServiceHandlerSystemException(self.service_name)
            seen_cursors.add(cursor)
            params = {**params, "cursor": cursor}

        LOG.debug("Fetched %d files in dataset %s", len(dataset_files), dataset_id)
        return dataset_files

    async def remove_ingested_file(self, dataset_id: str, accession_id: str) -> None:
        """Request the removal of a file from a dataset.

        The Admin API only queues the request, which can still fail without an error reported here.
        Use list_ingested_files to find out whether the file was removed.

        :param dataset_id: Dataset accession ID
        :param accession_id: Accession ID of the file
        """
        admin_auth_headers = self.get_admin_auth_headers()
        await self._send(
            method="DELETE",
            path=f"/dataset/{dataset_id}/files/{accession_id}",
            headers=admin_auth_headers,
        )
        LOG.info("Requested removal of file %s from dataset %s", accession_id, dataset_id)

    async def mark_file_removed(self, file_id: str, reason: str) -> None:
        """Log a removed event for a file, so that the user's inbox files no longer list it.

        Removing a file from a dataset does not change the file's own status, since a file can belong to
        several datasets. So the inbox of the user who uploaded the file lists it again.

        :param file_id: File ID of the file
        :param reason: Why the file is removed, stored with the event
        """
        admin_auth_headers = self.get_admin_auth_headers()
        await self._send(
            method="POST",
            path=f"/file/events/{file_id}/removed",
            json_data={"reason": reason},
            headers=admin_auth_headers,
        )
        LOG.info("Logged removed event for file %s", file_id)

    async def ingest_file(self, *, data: IngestFileRequest | None = None, file_id: str | None = None) -> None:
        """Start the ingestion of a file.

        :param data: Request data including 'user' and 'filepath'
        :param file_id: File ID of the file to be ingested
        """
        admin_auth_headers = self.get_admin_auth_headers()

        if data is None and file_id is None:
            raise SystemException("Either data or file_id must be provided for file ingestion")

        if data:
            ingestion_data = {"user": data.user, "filepath": data.filepath}
            await self._request(
                method="POST", path="/file/ingest", json_data=ingestion_data, headers=admin_auth_headers
            )
            LOG.debug("File with path %r is being ingested", data.filepath)

        if file_id:
            await self._request(
                method="POST", path="/file/ingest", params={"fileid": file_id}, headers=admin_auth_headers
            )
            LOG.debug("File with ID %s is being ingested", file_id)

    async def post_accession_id(
        self, *, data: PostAccessionIdRequest | None = None, file_id: str | None = None, accession_id: str | None = None
    ) -> None:
        """Assign accession ID to a file.

        :param data: Request data including 'user', 'filepath' and 'accessionId'
        :param file_id: File ID of the file to which the accession ID is assigned
        :param accession_id: Accession ID to assign
        """
        admin_auth_headers = self.get_admin_auth_headers()

        if data is None and (file_id is None or accession_id is None):
            raise SystemException("Either data or file_id and accession_id must be provided for posting accession ID")

        if data:
            accession_data = {"user": data.user, "filepath": data.filepath, "accession_id": data.accession_id}
            await self._request(
                method="POST", path="/file/accession", json_data=accession_data, headers=admin_auth_headers
            )
            LOG.debug("Accession ID %s assigned to file %s", data.accession_id, data.filepath)

        if file_id and accession_id:
            await self._request(
                method="POST",
                path="/file/accession",
                params={"fileid": file_id, "accessionid": accession_id},
                headers=admin_auth_headers,
            )
            LOG.debug("Accession ID %s assigned to file with ID %s", accession_id, file_id)

    async def create_dataset(self, data: CreateDatasetRequest) -> None:
        """Create dataset for user.

        :param data: Request data including 'user', 'accession_ids' and 'dataset_id'
        """
        admin_auth_headers = self.get_admin_auth_headers()
        dataset_data = {"user": data.user, "accession_ids": data.accession_ids, "dataset_id": data.dataset_id}
        await self._request(method="POST", path="/dataset/create", json_data=dataset_data, headers=admin_auth_headers)
        LOG.info("Dataset %s has been created", dataset_data["dataset_id"])

    async def release_dataset(self, dataset: str) -> None:
        """Release dataset for user.

        :param dataset: Dataset accession ID
        """
        admin_auth_headers = self.get_admin_auth_headers()
        await self._request(method="POST", path=f"/dataset/release/{dataset}", headers=admin_auth_headers)
        LOG.info("Dataset %s has been released", dataset)

    async def get_dataset_status(self, dataset: str) -> DatasetStatus | None:
        """Return the current status of a dataset.

        :param dataset: Dataset accession ID
        :returns: the dataset's status, or ``None`` if the Admin API has no record of it yet (not
            created, or reported with a status this client does not recognise).
        """
        admin_auth_headers = self.get_admin_auth_headers()

        try:
            dataset_resp: dict[str, Any] = await self._request(
                method="GET", path=f"/dataset/{dataset}", headers=admin_auth_headers
            )
        except ServiceHandlerSystemException as e:
            if e.service_status_code == status.HTTP_404_NOT_FOUND:
                return None
            raise

        raw_status = self._validate_response(GetDatasetResponse, dataset_resp).status
        if raw_status is None:
            return None

        try:
            return DatasetStatus(raw_status)
        except ValueError:
            LOG.warning("Unknown dataset status %r for dataset %s", raw_status, dataset)
            return None
