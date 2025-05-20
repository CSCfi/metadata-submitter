"""Project operator class."""

from aiohttp import web
from pymongo.errors import ConnectionFailure, OperationFailure

from ...helpers.logger import LOG
from .base import BaseOperator


class ProjectOperator(BaseOperator):
    """ObjectOperator class for handling database operations of project groups.

    Operations are implemented with JSON format.
    """

    async def create_project(self, project_number: str) -> str:
        """Create new object project to database.

        :param project_number: project external ID received from AAI
        :raises: HTTPBadRequest if error occurs during the process of insert
        :returns: Project id for the project inserted to database
        """
        project_data: dict[str, str | list[str]] = {}

        try:
            existing_project_id: None | str = await self.db_service.exists_project_by_external_id(project_number)
            if existing_project_id:
                LOG.info("Project with external ID: %r exists, no need to create.", project_number)
                return existing_project_id

            project_id = self._generate_accession_id()
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
