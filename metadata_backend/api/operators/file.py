"""File operator class."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from aiohttp import web
from pymongo.errors import ConnectionFailure, OperationFailure

from ...helpers.logger import LOG
from ...helpers.validator import JSONValidator
from ..services.accession import generate_bp_accession, generate_default_accession
from .base import BaseOperator


@dataclass
class File:
    """File class that should be used for handling a file version."""

    name: str
    path: str
    projectId: str

    # specific to each file version
    bytes: int
    encrypted_checksums: list[dict[str, str]]
    unencrypted_checksums: list[dict[str, str]]


class FileOperator(BaseOperator):
    """FileOperator class for handling database operations of files."""

    def _get_file_version_date(self) -> int:
        """Get current time."""
        return int(datetime.now().timestamp())

    async def _get_file_id_and_version(
        self, path: str, project_id: str, is_bigpicture: bool = False
    ) -> dict[str, str | int]:
        """Get an accession id and file version for a file.

        Checks if file already exists. Generates data if file not found in db.

        :param path: file path
        :param project_id: project id of file
        :param is_bigpicture: specify if the file belongs to Bigpicture
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        :returns: dict with file accession id and file version
        """
        try:
            file = await self.check_file_exists(project_id, path)
            if file:
                accession_id = file["accessionId"]
                version = file["currentVersion"]["version"] + 1
            else:
                accession_id = generate_bp_accession("bpfile") if is_bigpicture else generate_default_accession()
                version = 1
            return {"accessionId": accession_id, "version": version}
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while reading file info: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error

    async def form_validated_file_object(self, file: File, is_bigpicture: bool = False) -> dict[str, Any]:
        """Formulate a file object from File fit for inserting to db.

        Checks if file with the same path already exists.

        :param file: File with all class properties
        :param is_bigpicture: specify if the file belongs to Bigpicture
        :returns: validated file object according to file.json schema
        """
        id_and_version = await self._get_file_id_and_version(file.path, file.projectId, is_bigpicture)
        LOG.info(id_and_version)

        file_object = {
            "accessionId": id_and_version["accessionId"],
            "name": file.name,
            "path": file.path,
            "projectId": file.projectId,
            "versions": [
                {
                    "date": self._get_file_version_date(),
                    "version": id_and_version["version"],
                    "bytes": file.bytes,
                    "submissions": [],
                    "published": False,
                    "encrypted_checksums": file.encrypted_checksums,
                    "unencrypted_checksums": file.unencrypted_checksums,
                }
            ],
            "flagDeleted": False,
        }
        JSONValidator(file_object, "file").validate()
        return file_object

    async def _create_file(self, file: dict[str, Any]) -> dict[str, str | int]:
        """Add a new file object to database.

        :param file: file data as in the `file.json` schema
        :raises: HTTPBadRequest if file creation in the db was not successful
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        :returns: dict with file accession id and file version
        """
        try:
            insert_success = await self.db_service.create("file", file)
            if not insert_success:
                reason = "Inserting file to database failed for some reason."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
            return {"accessionId": file["accessionId"], "version": file["versions"][0]["version"]}
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while inserting a new file to DB: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error

    async def create_file_or_version(self, file: dict[str, Any]) -> dict[str, str | int]:
        """Add a new file or file version to database.

        :param file: file data as in the `file.json` schema
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        :returns: dict with file accession id and file version
        """
        created_file: dict[str, str | int]
        file_version = file["versions"][0]["version"]

        if file_version == 1:
            # Create a new file
            created_file = await self._create_file(file)
        elif file_version > 1:
            # Create a new file version. Reset flagDeleted.
            try:
                await self.db_service.patch(
                    "file",
                    file["accessionId"],
                    [
                        {"op": "add", "path": "/versions/-", "value": file["versions"][0]},
                        {"op": "replace", "path": "/flagDeleted", "value": False},
                    ],
                )
                created_file = {"accessionId": file["accessionId"], "version": file_version}
            except (ConnectionFailure, OperationFailure) as error:
                reason = f"Error happened while inserting a new file version: {error}"
                LOG.exception(reason)
                raise web.HTTPInternalServerError(reason=reason) from error
        else:
            reason = "Cannot create file: invalid file version."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info(
            "Inserting file with ID %r and version %d to database succeeded.",
            created_file["accessionId"],
            created_file["version"],
        )
        return created_file

    async def read_file(self, accession_id: str, version: Optional[int] = None) -> dict[str, Any]:
        """Read file object from database.

        :param accession_id: Accession ID of the file to read
        :param version: version number to extract. Defaults to latest
        :raises: HTTPBadRequest if reading was not successful
        :raises: HTTPNotFound if file not found
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        :returns: File object of the latest file version
        """
        aggregate_query = [
            {"$match": {"accessionId": accession_id}},
            {"$unwind": "$versions"},
            {
                "$project": {
                    "_id": 0,
                    "name": 1,
                    "path": 1,
                    "projectId": 1,
                    "flagDeleted": 1,
                    "bytes": "$versions.bytes",
                    "encrypted_checksums": "$versions.encrypted_checksums",
                    "unencrypted_checksums": "$versions.unencrypted_checksums",
                }
            },
        ]
        if version:
            # get a specific version
            aggregate_query.insert(2, {"$match": {"versions.version": version}})
        else:
            # sort to get the latest version
            aggregate_query.insert(2, {"$sort": {"versions.version": -1}})
            # get only the latest version
            aggregate_query.insert(3, {"$limit": 1})
        try:
            file: list[dict[str, Any]] = await self.db_service.do_aggregate("file", aggregate_query)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting file, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error
        if not file:
            reason = f"File '{accession_id}' was not found."
            if version:
                reason = f"File '{accession_id}' (version: '{version}') was not found."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

        return file[0]

    async def read_project_files(self, project_id: str) -> list[dict[str, Any]]:
        """Read files from DB based on a specific filter type and corresponding identifier.

        Returns the latest file version, filtered by projectId and flagDeleted.

        :param project_id: Project ID to get files for
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        :returns: List of files
        """
        aggregate_query = [
            {"$match": {"projectId": project_id, "flagDeleted": False}},
            {
                "$project": {
                    "_id": 0,
                    "accessionId": 1,
                    "name": 1,
                    "path": 1,
                    "projectId": 1,
                    "version": {"$last": "$versions.version"},
                    "bytes": {"$last": "$versions.bytes"},
                    "encrypted_checksums": {"$last": "$versions.encrypted_checksums"},
                    "unencrypted_checksums": {"$last": "$versions.unencrypted_checksums"},
                }
            },
        ]
        try:
            result: list[dict[str, Any]] = await self.db_service.do_aggregate("file", aggregate_query)
            return result
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting files for project {project_id}, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error

    async def flag_file_deleted(self, file: dict[str, Any], deleted: bool = True) -> None:
        """Flag file as deleted.

        File should not be deleted from DB, only flagged as not available anymore

        :param file: file dict
        :param deleted: Whether file is marked as deleted, set to `False` to mark a file as available again
        :raises: HTTPBadRequest if deleting was not successful
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        """
        try:
            delete_success = await self.db_service.update_by_key_value(
                "file", {"path": file["path"], "projectId": file["projectId"]}, {"flagDeleted": deleted}
            )
            await self.remove_file_submission(file["accessionId"], file["path"])
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while flagging file as deleted, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error
        if not delete_success:
            reason = f"Flagging file with path: {file['path']} as deleted failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("Flagging file with file_path: %r as Deleted succeeded.", file["path"])

    async def remove_file_submission(
        self,
        accession_id: str,
        file_path: Optional[str] = None,
        submission_id: Optional[str] = None,
    ) -> None:
        """Remove file from a submission or all submissions. Submission(s) should not be published yet.

        :param accession_id: Accession ID of the file to remove from submission
        :param file_path: path of the file to be removed
        :param submission_id: Submission ID to remove file associated with it
        :raises: HTTPBadRequest if deleting was not successful
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        """
        try:
            if submission_id:
                delete_success = await self.db_service.remove(
                    "submission", submission_id, {"files": {"accessionId": accession_id}}
                )
                LOG.info("Removing file: %r from submission: %r succeeded.", accession_id, submission_id)
            elif file_path:
                delete_success = await self.db_service.remove_many(
                    "submission", {"files": {"accessionId": accession_id}}, {"published": False}
                )
                LOG.info(
                    "Removing file with path: %r from submissions, by accessionID: %r succeeded.",
                    file_path,
                    accession_id,
                )
            else:
                reason = f"Cannot recognize path or submission ID of file with accession ID: {accession_id}"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while removing file from submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error
        if not delete_success:
            reason = f"Removing file by accession ID: {accession_id} from submission failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def check_file_exists(self, project_id: str, file_path: str) -> None | dict[str, Any]:
        """Check if file already exists in the database.

        :param project_id: project ID of the file
        :param file_path: path of the file
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        :returns: file document if file_path is found
        """
        _projection = {
            "_id": 0,
            "accessionId": 1,
            "path": 1,
            "projectId": 1,
            # get only the last version of a file
            "currentVersion": {"$first": {"$sortArray": {"input": "$versions", "sortBy": {"version": -1}}}},
        }

        try:
            file_in_db: None | dict[str, Any] = await self.db_service.read_by_key_value(
                "file", {"path": file_path, "projectId": project_id}, _projection
            )
            return file_in_db
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while reading file info: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error
