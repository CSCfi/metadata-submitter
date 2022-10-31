"""Project operator class."""
from typing import Dict, List, Union

from aiohttp import web
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, OperationFailure

from ...conf.conf import mongo_database
from ...database.db_service import DBService
from ...helpers.logger import LOG
from .common import _generate_accession_id


class ProjectOperator:
    """ObjectOperator class for handling database operations of project groups.

    Operations are implemented with JSON format.
    """

    def __init__(self, db_client: AsyncIOMotorClient) -> None:
        """Init db_service.

        :param db_client: Motor client used for database connections. Should be
        running on same loop with aiohttp, so needs to be passed from aiohttp
        Application.
        """
        self.db_service = DBService(mongo_database, db_client)

    async def create_project(self, project_number: str) -> str:
        """Create new object project to database.

        :param project_number: project external ID received from AAI
        :raises: HTTPBadRequest if error occurs during the process of insert
        :returns: Project id for the project inserted to database
        """
        project_data: Dict[str, Union[str, List[str]]] = {}

        try:
            existing_project_id = await self.db_service.exists_project_by_external_id(project_number)
            if existing_project_id:
                LOG.info("Project with external ID: %r exists, no need to create.", project_number)
                return existing_project_id

            project_id = _generate_accession_id()
            project_data["templates"] = []
            project_data["projectId"] = project_id
            project_data["externalId"] = project_number
            insert_success = await self.db_service.create("project", project_data)
            if not insert_success:
                reason = "Inserting project to database failed for some reason."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)

            LOG.info("Inserting project with ID: %r to database succeeded.", project_id)
            return project_id
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while inserting project: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

    async def check_project_exists(self, project_id: str) -> None:
        """Check the existence of a project by its id in the database.

        :param project_id: Identifier of project to find.
        :raises: HTTPNotFound if project does not exist
        """
        exists = await self.db_service.exists("project", project_id)
        if not exists:
            reason = f"Project with ID: '{project_id}' was not found."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

    async def assign_templates(self, project_id: str, object_ids: List) -> None:
        """Assing templates to project.

        :param project_id: ID of project to update
        :param object_ids: ID or list of IDs of template(s) to assign
        :raises: HTTPBadRequest if assigning templates to project was not successful
        returns: None
        """
        try:
            await self.check_project_exists(project_id)
            assign_success = await self.db_service.append(
                "project", project_id, {"templates": {"$each": object_ids, "$position": 0}}
            )
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting project, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

        if not assign_success:
            reason = "Assigning templates to project failed."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("Assigning templates: %r to project: %r succeeded.", object_ids, project_id)

    async def remove_templates(self, project_id: str, object_ids: List) -> None:
        """Remove templates from project.

        :param project_id: ID of project to update
        :param object_ids: ID or list of IDs of template(s) to remove
        :raises: HTTPBadRequest if db connection fails
        returns: None
        """
        remove_content: Dict
        try:
            await self.check_project_exists(project_id)
            for obj in object_ids:
                remove_content = {"templates": {"accessionId": obj}}
                await self.db_service.remove("project", project_id, remove_content)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while removing templates from project, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("Removing templates: %r from project: %r succeeded.", ", ".join(object_ids), project_id)

    async def update_project(self, project_id: str, patch: List) -> str:
        """Update project object in database.

        :param project_id: ID of project to update
        :param patch: Patch operations determined in the request
        :returns: ID of the project updated to database
        """
        try:
            await self.check_project_exists(project_id)
            update_success = await self.db_service.patch("project", project_id, patch)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting project, err: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

        if not update_success:
            reason = "Updating project in database failed for some reason."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        LOG.info("Updating project: %r to database succeeded.", project_id)
        return project_id
