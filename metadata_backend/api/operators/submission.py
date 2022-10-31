"""Submission operator class."""
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union

from aiohttp import web
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, OperationFailure

from ...conf.conf import mongo_database
from ...database.db_service import DBService
from ...helpers.logger import LOG
from .common import _generate_accession_id


class SubmissionOperator:
    """ObjectOperator class for handling database operations of submissions.

    Operations are implemented with JSON format.
    """

    def __init__(self, db_client: AsyncIOMotorClient) -> None:
        """Init db_service.

        :param db_client: Motor client used for database connections. Should be
        running on same loop with aiohttp, so needs to be passed from aiohttp
        Application.
        """
        self.db_service = DBService(mongo_database, db_client)

    async def get_submission_field(self, submission_id: str, field: str) -> Union[str, list, dict]:
        """Get a field from the submission.

        :param submission_id: internal accession ID of submission
        :param field: field name
        :returns: field value
        """
        try:
            submission_cursor = self.db_service.query(
                "submission", {"submissionId": submission_id}, {"_id": False, field: 1}, limit=1
            )
            submissions = [submission async for submission in submission_cursor]
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPInternalServerError(reason=reason) from error
        except AttributeError as error:
            reason = f"Submission '{submission_id}' doesn't have the requested '{field}' field."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason) from error

        if len(submissions) == 1:
            try:
                return submissions[0][field]
            except KeyError as error:
                # This should not be possible and should never happen, if the submission was created properly
                reason = f"Submission: '{submission_id}' does not have a value for '{field}', err: {error}"
                LOG.exception(reason)
                raise web.HTTPBadRequest(reason=reason) from error

        reason = f"Submission: '{submission_id}' not found."
        LOG.error(reason)
        raise web.HTTPBadRequest(reason=reason)

    async def get_submission_field_str(self, submission_id: str, field: str) -> str:
        """Get a string field from the submission.

        :param submission_id: internal accession ID of submission
        :param field: field name
        :returns: string value
        """
        value = await self.get_submission_field(submission_id, field)
        if isinstance(value, str):
            return value

        reason = (
            f"Submission: '{submission_id}' has an invalid {field}, "
            f"expected 'str', got {type(value)}. This is a bug."
        )
        LOG.error(reason)
        raise web.HTTPInternalServerError(reason=reason)

    async def get_submission_field_list(self, submission_id: str, field: str) -> list:
        """Get an array field from the submission.

        :param submission_id: internal accession ID of submission
        :param field: field name
        :returns: list value
        """
        value = await self.get_submission_field(submission_id, field)
        if isinstance(value, list):
            return value

        reason = (
            f"Submission: '{submission_id}' has an invalid {field}, expected 'list', "
            f"got {type(value)}. This is a bug."
        )
        LOG.error(reason)
        raise web.HTTPInternalServerError(reason=reason)

    async def get_submission_project(self, submission_id: str) -> str:
        """Get the project ID the submission is associated to.

        :param submission_id: internal accession ID of submission
        :returns: project ID submission is associated to
        """
        return await self.get_submission_field_str(submission_id, "projectId")

    async def check_object_in_submission(self, collection: str, accession_id: str) -> Tuple[str, bool]:
        """Check a object/draft is in a submission.

        :param collection: collection it belongs to, it would be used as path
        :param accession_id: document by accession_id
        :raises: HTTPUnprocessableEntity if error occurs during the process and object in more than 1 submission
        :returns: Tuple with submission id if object is in submission and bool if published or not
        """
        try:
            submission_path = "drafts" if collection.startswith("draft") else "metadataObjects"

            submission_cursor = self.db_service.query(
                "submission", {submission_path: {"$elemMatch": {"accessionId": accession_id, "schema": collection}}}
            )
            submission_check = [submission async for submission in submission_cursor]
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while checking object in submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

        if len(submission_check) == 0:
            LOG.info("Doc with accession ID: %r belongs to no submission something is off", accession_id)
            return "", False

        if len(submission_check) > 1:
            reason = f"The {accession_id} is in more than 1 submission."
            LOG.error(reason)
            raise web.HTTPUnprocessableEntity(reason=reason)

        submission_id = submission_check[0]["submissionId"]
        LOG.info("Found doc with accession ID: %r in submission: %r.", accession_id, submission_id)
        return submission_id, submission_check[0]["published"]

    async def get_collection_objects(self, submission_id: str, collection: str) -> List:
        """List objects ids per collection.

        :param submission_id: id of the submission
        :param collection: collection it belongs to, it would be used as path
        :returns: List of objects
        """
        try:
            submission_path = "drafts" if collection.startswith("draft") else "metadataObjects"

            submission_cursor = self.db_service.query(
                "submission",
                {"$and": [{submission_path: {"$elemMatch": {"schema": collection}}}, {"submissionId": submission_id}]},
            )
            submissions = [submission async for submission in submission_cursor]
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting collection objects, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

        if len(submissions) >= 1:
            return [i["accessionId"] for i in submissions[0][submission_path]]

        return []

    async def create_submission(self, data: Dict) -> str:
        """Create new object submission to database.

        :param data: Data to be saved to database
        :raises: HTTPBadRequest if error occurs during the process of insert
        :returns: Submission id for the submission inserted to database
        """
        submission_id = _generate_accession_id()
        _now = int(datetime.now().timestamp())
        data["submissionId"] = submission_id
        data["text_name"] = " ".join(re.split("[\\W_]", data["name"]))
        data["published"] = False
        data["dateCreated"] = _now
        # when we create a submission the last modified should correspond to dateCreated
        data["lastModified"] = _now
        data["metadataObjects"] = data["metadataObjects"] if "metadataObjects" in data else []
        data["drafts"] = data["drafts"] if "drafts" in data else []
        try:
            insert_success = await self.db_service.create("submission", data)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while inserting submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

        if not insert_success:
            reason = "Inserting submission to database failed for some reason."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("Inserting submission with ID: %r to database succeeded.", submission_id)
        return submission_id

    async def query_submissions(
        self, query: Dict, page_num: int, page_size: int, sort_param: Optional[dict] = None
    ) -> Tuple[List, int]:
        """Query database based on url query parameters.

        :param query: Dict containing query information
        :param page_num: Page number
        :param page_size: Results per page
        :param sort_param: Sorting options.
        :returns: Tuple with Paginated query result
        """
        skips = page_size * (page_num - 1)

        if not sort_param:
            sort = {"dateCreated": -1}
        elif sort_param["score"] and not sort_param["date"] and not sort_param["modified"]:
            sort = {"score": {"$meta": "textScore"}, "dateCreated": -1}  # type: ignore
        elif sort_param["score"] and sort_param["date"]:
            sort = {"dateCreated": -1, "score": {"$meta": "textScore"}}  # type: ignore
        elif sort_param["score"] and sort_param["modified"]:
            sort = {"lastModified": -1, "score": {"$meta": "textScore"}}  # type: ignore
        else:
            sort = {"dateCreated": -1}

        _query = [
            {"$match": query},
            {"$sort": sort},
            {"$skip": skips},
            {"$limit": page_size},
            {"$project": {"_id": 0, "text_name": 0}},
        ]
        data_raw = await self.db_service.do_aggregate("submission", _query)

        if not data_raw:
            data = []
        else:
            data = list(data_raw)

        count_query = [{"$match": query}, {"$count": "total"}]
        total_submissions = await self.db_service.do_aggregate("submission", count_query)

        if not total_submissions:
            total_submissions = [{"total": 0}]

        return data, total_submissions[0]["total"]

    async def read_submission(self, submission_id: str) -> Dict:
        """Read object submission from database.

        :param submission_id: Submission ID of the object to read
        :raises: HTTPBadRequest if reading was not successful
        :returns: Object submission formatted to JSON
        """
        try:
            submission = await self.db_service.read("submission", submission_id)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)
        return submission

    async def update_submission(self, submission_id: str, patch: List, schema: str = "") -> str:
        """Update object submission from database.

        Utilizes JSON Patch operations specified at: http://jsonpatch.com/

        :param submission_id: ID of submission to update
        :param patch: JSON Patch operations determined in the request
        :param schema: database schema for the object
        :raises: HTTPBadRequest if updating was not successful
        :returns: ID of the submission updated to database
        """
        try:
            if schema == "study":
                update_success = await self.db_service.update_study("submission", submission_id, patch)
            else:
                update_success = await self.db_service.patch("submission", submission_id, patch)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while updating submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

        if not update_success:
            if schema == "study":
                reason = "Either there was a request to add another study to a submissions or annother error occurred."
            else:
                reason = "Updating submission to database failed for some reason."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("Updating submission with ID: %r to database succeeded.", submission_id)
        return submission_id

    async def remove_object(self, submission_id: str, collection: str, accession_id: str) -> None:
        """Remove object from submissions in the database.

        :param submission_id: ID of submission to update
        :param accession_id: ID of object to remove
        :param collection: collection where to remove the id from
        :raises: HTTPBadRequest if db connection fails
        """
        try:
            submission_path = "drafts" if collection.startswith("draft") else "metadataObjects"
            upd_content = {submission_path: {"accessionId": accession_id}}
            await self.db_service.remove("submission", submission_id, upd_content)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while removing object from submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("Removing doc with accession ID: %r from submission: %r succeeded.", accession_id, submission_id)

    async def delete_submission(self, submission_id: str) -> Union[str, None]:
        """Delete object submission from database.

        :param submission_id: ID of the submission to delete
        :raises: HTTPBadRequest if deleting was not successful
        :returns: ID of the submission deleted from database
        """
        try:
            delete_success = await self.db_service.delete("submission", submission_id)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while deleting submission, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)
        if not delete_success:
            reason = f"Deleting for {submission_id} from database failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("Deleting submission with ID: %r to database succeeded.", submission_id)
        return submission_id

    async def check_submission_exists(self, submission_id: str) -> None:
        """Check the existance of a submission by its id in the database.

        :param submission_id: ID of the submission to check
        :raises: HTTPNotFound if submission does not exist
        """
        exists = await self.db_service.exists("submission", submission_id)
        if not exists:
            reason = f"Submission with ID: '{submission_id}' was not found."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

    async def check_submission_published(self, submission_id: str, method: str) -> None:
        """Check the published status of a submission by its id in the database.

        :param submission_id: ID of the submission to check
        :param method: Name of HTTP method used when this check is executed
        :raises: HTTPMethodNotAllowed if submission is not published
        """
        published = await self.db_service.published_submission(submission_id)
        if published:
            reason = f"Submission with ID: '{submission_id}' is already published and cannot be modified or deleted."
            LOG.error(reason)
            raise web.HTTPMethodNotAllowed(method=method, allowed_methods=["GET", "HEAD"], reason=reason)
