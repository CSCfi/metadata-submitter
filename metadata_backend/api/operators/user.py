"""User operator class."""
from typing import Dict, List, Tuple, Union

import aiohttp_session
from aiohttp import web
from pymongo.errors import ConnectionFailure, OperationFailure

from ...helpers.logger import LOG
from ...helpers.validator import JSONValidator
from .base import BaseOperator
from .object import ObjectOperator
from .submission import SubmissionOperator


class UserOperator(BaseOperator):
    """ObjectOperator class for handling database operations of users.

    Operations are implemented with JSON format.
    """

    async def check_user_has_doc(
        self, req: web.Request, collection: str, user_id: str, accession_id: str
    ) -> Tuple[bool, str]:
        """Check a submission/template belongs to same project the user is in.

        :param req: HTTP request
        :param collection: collection it belongs to, it would be used as path
        :param user_id: user_id from session
        :param accession_id: document by accession_id
        :raises: HTTPUnprocessableEntity if more users seem to have same submission
        :returns: True and project_id if accession_id belongs to user, False otherwise
        """
        session = await aiohttp_session.get_session(req)
        LOG.debug(
            "check that user %r belongs to same project as %r and has doc with accession ID:' %s'",
            user_id,
            collection,
            accession_id,
        )

        db_client = req.app["db_client"]
        user_operator = UserOperator(db_client)

        project_id = ""
        if collection.startswith("template"):
            object_operator = ObjectOperator(db_client)
            project_id = await object_operator.get_object_project(collection, accession_id)
        elif collection == "submission":
            submission_operator = SubmissionOperator(db_client)
            project_id = await submission_operator.get_submission_project(accession_id)
        else:
            reason = f"collection must be submission or template, received {collection}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        current_user = session["user_info"]
        user = await user_operator.read_user(current_user)
        user_has_project = await user_operator.check_user_has_project(project_id, user["userId"])
        return user_has_project, project_id

    async def check_user_has_project(self, project_id: str, user_id: str) -> bool:
        """Check that user has project affiliation.

        :param project_id: internal project ID
        :param user_id: internal user ID
        :raises HTTPBadRequest: on database error
        :returns: True if user has project, False if user does not have project
        """
        try:
            user_query = {"projects": {"$elemMatch": {"projectId": project_id}}, "userId": user_id}
            user_cursor = self.db_service.query("user", user_query)
            user_check = [user async for user in user_cursor]
            if user_check:
                LOG.debug("User: %r has project: %r affiliation.", user_id, project_id)
                return True

            reason = f"user {user_id} does not have project {project_id} affiliation"
            LOG.debug(reason)
            return False
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while reading user project affiliation, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def create_user(self, data: Dict[str, Union[list, str]]) -> str:
        """Create new user object to database.

        :param data: User Data to identify user
        :raises: HTTPBadRequest if error occurs during the process of creating user
        :returns: User id for the user object inserted to database
        """
        user_data: Dict[str, Union[list, str]] = {}

        try:
            existing_user_id = await self.db_service.exists_user_by_external_id(data["user_id"], data["real_name"])
            if existing_user_id:
                LOG.info("User with ID: %r  exists, no need to create.", data["user_id"])
                return existing_user_id

            user_data["projects"] = data["projects"]
            user_data["userId"] = user_id = self._generate_accession_id()
            user_data["name"] = data["real_name"]
            user_data["externalId"] = data["user_id"]
            JSONValidator(user_data, "users")
            insert_success = await self.db_service.create("user", user_data)
            if not insert_success:
                reason = "Inserting user to database failed for some reason."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)

            LOG.info("Inserting user with ID: %r to database succeeded.", user_id)
            return user_id
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while inserting user, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def read_user(self, user_id: str) -> Dict:
        """Read user object from database.

        :param user_id: User ID of the object to read
        :raises: HTTPBadRequest if reading user was not successful
        :returns: User object formatted to JSON
        """
        try:
            await self._check_user_exists(user_id)
            user = await self.db_service.read("user", user_id)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting user, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)
        return user

    async def update_user(self, user_id: str, patch: List) -> str:
        """Update user object from database.

        :param user_id: ID of user to update
        :param patch: Patch operations determined in the request
        :returns: User Id updated to database
        """
        try:
            await self._check_user_exists(user_id)
            update_success = await self.db_service.patch("user", user_id, patch)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while updating user, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

        if not update_success:
            reason = "Updating user to database failed for some reason."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("Updating user with ID: %r to database succeeded.", user_id)
        return user_id

    async def delete_user(self, user_id: str) -> str:
        """Delete user object from database.

        :param user_id: ID of the user to delete.
        :raises: HTTPBadRequest if deleting user was not successful
        :returns: User Id deleted from database
        """
        try:
            await self._check_user_exists(user_id)
            delete_success = await self.db_service.delete("user", user_id)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while deleting user, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)
        if not delete_success:
            reason = "Deleting for {user_id} from database failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("User with ID: %r successfully deleted.", user_id)
        return user_id

    async def _check_user_exists(self, user_id: str) -> None:
        """Check the existance of a user by its id in the database.

        :param user_id: Identifier of user to find.
        :raises: HTTPNotFound if user does not exist
        :returns: None
        """
        exists = await self.db_service.exists("user", user_id)
        if not exists:
            reason = f"User with ID: '{user_id}' was not found."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)
