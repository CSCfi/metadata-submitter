"""File operator class."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import ujson
from aiohttp import web
from pymongo.errors import ConnectionFailure, OperationFailure

from ...helpers.logger import LOG
from ...helpers.validator import JSONValidator
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

    async def _get_file_id_and_version(self, path: str, project_id: str) -> dict[str, str | int]:
        """Get an accession id and file version for a file.

        Checks if file already exists. Generates data if file not found in db.

        :param path: file path
        :param project_id: project id of file
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        :returns: dict with file accession id and file version
        """
        # Check if file already exists
        _projection = {
            "_id": 0,
            "accessionId": 1,
            # get only the last version of a file
            "currentVersion": {"$first": {"$sortArray": {"input": "$versions", "sortBy": {"version": -1}}}},
        }
        try:
            file_in_db = await self.db_service.read_by_key_value(
                "file", {"path": path, "projectId": project_id}, _projection
            )
            if file_in_db:
                accession_id = file_in_db["accessionId"]
                version = file_in_db["currentVersion"]["version"] + 1
            else:
                accession_id = self._generate_accession_id()
                version = 1
            return {"accessionId": accession_id, "version": version}
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while reading file info: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error

    async def form_validated_file_object(self, file: File) -> dict[str, Any]:
        """Formulate a file object from File fit for inserting to db.

        Checks if file with the same path already exists.

        :param file: File with all class properties
        :returns: validated file object according to file.json schema
        """
        id_and_version = await self._get_file_id_and_version(file.path, file.projectId)
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
        JSONValidator(file_object, "file").validate
        return file_object

    async def _create_file(self, file: dict[str, Any]) -> tuple[str, int]:
        """Add a new file object to database.

        :param file: file data as in the `file.json` schema
        :raises: HTTPBadRequest if file creation in the db was not successful
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        :returns: tuple of file accession id and file version
        """
        try:
            insert_success = await self.db_service.create("file", file)
            if not insert_success:
                reason = "Inserting file to database failed for some reason."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
            return file["accessionId"], file["versions"][0]["version"]
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while inserting a new file to DB: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error

    async def create_file_or_version(self, file: dict[str, Any]) -> tuple[str, int]:
        """Add a new file or file version to database.

        :param file: file data as in the `file.json` schema
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        :returns: tuple of file accession id and file version
        """
        created_file: tuple[str, int]
        file_version = file["versions"][0]["version"]

        if file_version == 1:
            # Create a new file
            created_file = await self._create_file(file)
        elif file_version > 1:
            # Create a new file version
            try:
                await self.db_service.append(
                    "file",
                    file["accessionId"],
                    {"versions": file["versions"]},
                    upsert=True,
                )
                created_file = file["accessionId"], file_version
            except (ConnectionFailure, OperationFailure) as error:
                reason = f"Error happened while inserting a new file version: {error}"
                LOG.exception(reason)
                raise web.HTTPInternalServerError(reason=reason) from error
        else:
            reason = "Cannot create file: invalid file version."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("Inserting file with ID %r and version %d to database succeeded.", created_file[0], created_file[1])
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
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

        return file[0]

    async def read_project_files(self, project_id: str) -> list[dict[str, Any]]:
        """Read files from DB based on a specific filter type and corresponding identifier.

        The files are read by the latest version, and filtered either by projectId.

        :param project_id: Project ID to get files for
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        :returns: List of files
        """
        aggregate_query = [
            {"$match": {"projectId": project_id}},
            {"$sort": {"versions.version": -1}},
            {"$unwind": "$versions"},
            {
                "$project": {
                    "_id": 0,
                    "accessionId": 1,
                    "name": 1,
                    "path": 1,
                    "projectId": 1,
                    "version": "$versions.version",
                    "bytes": "$versions.bytes",
                    "encrypted_checksums": "$versions.encrypted_checksums",
                    "unencrypted_checksums": "$versions.unencrypted_checksums",
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

    async def check_submission_files_ready(self, submission_id: str) -> None:
        """Check all files in a submission are marked as ready.

        Files marked as ready in a submission, means an metadata object has been
        attached to the file.

        :param submission_id: Submission ID to get associated files status
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        """
        aggregate_query = [
            {"$match": {"submissionId": submission_id}},
            {"$unwind": "$files"},
            # check the status is not in failed or added
            # failed can occour when an file ingestion/verification/mapping fails
            {"$match": {"files.status": {"$in": ["added", "failed"]}}},
            {
                "$project": {
                    "_id": 0,
                    "accessionId": "$files.accessionId",
                    "version": "$files.version",
                    "status": "$files.status",
                }
            },
        ]
        try:
            problematic_files = await self.db_service.do_aggregate("submission", aggregate_query)
            if len(problematic_files) > 0:
                reason = (
                    f"There are a problematic files: {','.join([i['accessionId'] for i in problematic_files])} "
                    f"in the submission with id: {submission_id}"
                )
                LOG.error(reason)
                raise web.HTTPBadRequest(
                    reason=reason,
                    text=ujson.dumps({"problematic-files": problematic_files}),
                    content_type="application/json",
                )
            LOG.debug("All files have been marked as ready")
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error

    async def read_submission_files(
        self, submission_id: str, expected_status: Optional[list[Any]] = None
    ) -> list[dict[str, Any]]:
        """Get files in a submission.

        The files are identified in a submission by version.

        :param submission_id: Submission ID to read files associated with a submission
        :param expected_status: List of expected statuses (can be one or more statuses)
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue or db aggregate does not return a list
        :returns: List of files specific to a submission
        """
        aggregate_query = [
            {"$match": {"submissionId": submission_id}},
            {"$unwind": "$files"},
            {"$project": {"_id": 0, "accessionId": "$files.accessionId", "version": "$files.version"}},
        ]
        if expected_status:
            # we match only the files that have a specific status
            aggregate_query.insert(
                2,
                {"$match": {"files.status": {"$in": expected_status}}},
            )
        files = []
        try:
            submission_files = await self.db_service.do_aggregate("submission", aggregate_query)
            if not isinstance(submission_files, list):
                reason = f"Reading submission files for '{submission_id}' failed"
                LOG.error(reason)
                raise web.HTTPInternalServerError(reason=reason)
            for file in submission_files:
                files.append(await self.read_file(file["accessionId"], file["version"]))

            return files
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error

    async def flag_file_deleted(self, file_path: str, deleted: bool = True) -> None:
        """Flag file as deleted.

        File should not be deleted from DB, only flagged as not available anymore

        :param file_path: Path of the file to flag as deleted
        :param deleted: Whether file is marked as deleted, set to `False` to mark a file as available again
        :raises: HTTPBadRequest if deleting was not successful
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        """
        try:
            delete_success = await self.db_service.update_by_key_value(
                "file", {"path": file_path}, {"flagDeleted": deleted}
            )
            await self.remove_file_submission(file_path, id_type="path")
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while flagging file as deleted, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error
        if not delete_success:
            reason = f"Flagging file with '{file_path}' as deleted failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("Flagging file with file_path: %r as Deleted succeeded.", file_path)

    async def remove_file_submission(
        self, id_or_path: str, id_type: Optional[str] = None, submission_id: Optional[str] = None
    ) -> None:
        """Remove file from a submission or all submissions.

        :param id_or_path: Accession ID or path of the file to remove from submission
        :param id_type: depending on the file id this can be either ``path`` or ``accessionId``.
        :param submission_id: Submission ID to remove file associated with it
        :raises: HTTPBadRequest if deleting was not successful
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        """
        _file: dict[str, Any] = {}
        try:
            if id_type == "path":
                _file = await self.db_service.read_by_key_value("file", {"path": id_or_path}, {"accessionId": 1})
            elif id_type == "accessionId":
                _file["accessionId"] = id_or_path
            else:
                reason = f"Cannot recognize '{id_type}' as a type of id for file deletion from submission."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
            if submission_id:
                delete_success = await self.db_service.remove(
                    "submission", submission_id, {"files": {"accessionId": _file["accessionId"]}}
                )
                LOG.info("Removing file: %r from submission: %r succeeded.", id_or_path, submission_id)
            else:
                delete_success = await self.db_service.remove_many(
                    "submission", {"files": {"accessionId": _file["accessionId"]}}
                )
                LOG.info(
                    "Removing file with path: %r from submissions, by accessionID: %r succeeded.",
                    id_or_path,
                    _file["accessionId"],
                )
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while removing file from submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error
        if not delete_success:
            reason = f"Removing file identified via '{id_type}': '{id_or_path}' from submission failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def update_file_submission(self, accession_id: str, submission_id: str, update_data: dict[str, Any]) -> None:
        """Update file in a submission.

        File should not be deleted from DB, only flagged as not available anymore

        :param accession_id: Accession ID of the file to update
        :param submission_id: Submission ID to update file associated with it
        :param update_data: Mongodb ``$set`` operation to be performed on the submission
        :raises: HTTPBadRequest if deleting was not successful
        :raises: HTTPInternalServerError if db operation failed because of connection
        or other db issue
        """
        try:
            update_success = await self.db_service.update_by_key_value(
                "submission",
                {"submissionId": submission_id, "files": {"$elemMatch": {"accessionId": accession_id}}},
                # this can take the form of: {"files.$.status": "failed"} or
                # {"files.$.status": "failed", "files.$.version": 3,
                # "files.$.objectId": {"accessionId": 4, "schema": "study"}
                # ideally we check before that we don't update the accessionId
                update_data,
            )
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while updating file in submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error
        if not update_success:
            reason = f"Updating file with '{accession_id}' in '{submission_id}' failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("Updating file with file ID: %r in submission %r succeeded.", accession_id, submission_id)

    async def add_files_submission(self, files: list[dict[str, Any]], submission_id: str) -> bool:
        """Add files to a submission.

        Doesn't check if files are already present in the submission.

        :param files: list of files according to submission schema
        :param submission_id: Submission ID to add files to
        :returns: True if operation to append was successful
        """
        success: bool = await self.db_service.append("submission", submission_id, {"files": {"$each": files}})
        return success

    async def check_submission_has_file(self, submission_id: str, file_id: str) -> bool:
        """Check if submission has a file with given accession id.

        :param submission_id: submission ID to check files of
        :param file_id: accession ID of file
        :returns: True if file found
        """
        submission = await self.db_service.read("submission", submission_id)
        if submission:
            for file in submission["files"]:
                if file["accessionId"] == file_id:
                    return True
        return False
