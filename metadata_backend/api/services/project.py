"""Service to verify that the user has access to the given projects."""

from abc import ABC, abstractmethod

from aiohttp import web

from ..models import Project
from . import ldap


class ProjectService(ABC):
    """Service to verify that the user has access to the given projects."""

    async def verify_user_project(self, user_id: str, project_id: str) -> None:
        """
        Verify that the user has access to the given project.

        Args:
            user_id: The user ID.
            project_id: The project ID.
        """
        if not await self._verify_user_project(user_id, project_id):
            raise web.HTTPUnauthorized(reason=f"User {user_id} is not affiliated with project {project_id}.")

    async def get_user_projects(self, user_id: str) -> list[Project]:
        """
        Return user's projects.

        Args:
            user_id: The user ID.
        """
        return await self._get_user_projects(user_id)

    @abstractmethod
    async def _verify_user_project(self, user_id: str, project_id: str) -> bool:
        """
        Verify that the user has access to the given project.

        Args:
            user_id: The user ID.
            project_id: The project ID.

        Returns:
            True if the user has access to the given project.
        """

    @abstractmethod
    async def _get_user_projects(self, user_id: str) -> list[Project]:
        """
        Return user's projects.

        Args:
            user_id: The user ID.
        """


class CscLdapProjectService(ProjectService):
    """Service to verify that the user has access to the given project using CSC's LDAP service.."""

    async def _verify_user_project(self, user_id: str, project_id: str) -> bool:
        """
        Verify that the specified user has access to the given project.

        Args:
            user_id: The user ID.
            project_id: The project ID.

        Returns:
            True if the user has access to the given project.
        """
        return ldap.verify_user_project(user_id, project_id)

    async def _get_user_projects(self, user_id: str) -> list[Project]:
        """
        Return user's projects.

        Args:
            user_id: The user ID.
        """
        return [Project(project_id=project_id) for project_id in ldap.get_user_projects(user_id)]
