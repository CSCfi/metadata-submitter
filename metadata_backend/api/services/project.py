"""Service to verify that the user has access to the given projects."""

import json
from abc import ABC, abstractmethod
from typing import override
from urllib.parse import urlparse

from aiocache import SimpleMemoryCache, cached
from aiohttp import web
from ldap3 import Connection, Server

from ...conf.ldap import csc_ldap_config
from ...helpers.logger import LOG
from ..exceptions import SystemException, UserException
from ..models.models import Project

CSC_LDAP_DN = "ou=idm,dc=csc,dc=fi"
CSC_LDAP_PROJECT_ATTRIBUTE = "CSCPrjNum"
CSC_LDAP_SERVICE_PROFILE = "SP_SD-SUBMIT"
CSC_LDAP_FILTER = "(&(objectClass=applicationProcess)(CSCSPCommonStatus=ready)(CSCUserName={username}))"


class ProjectService(ABC):
    """Service to verify that the user has access to the given projects."""

    @cached(ttl=3600, cache=SimpleMemoryCache)  # type: ignore
    async def verify_user_project(self, user_id: str, project_id: str) -> None:
        """
        Verify that the user has access to the given project.

        Args:
            user_id: The user ID.
            project_id: The project ID.
        """
        if not await self._verify_user_project(user_id, project_id):
            raise web.HTTPUnauthorized(reason=f"User {user_id} is not affiliated with project {project_id}.")

    @cached(ttl=3600, cache=SimpleMemoryCache)  # type: ignore
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

        Returns:
            The user's projects.
        """

    async def get_project_id(self, user_id: str) -> str:
        """
        Returns a single project id associated with the user. Raises an UserException if
        the user is not associated with a single project.

        :param user_id: The user id
        :returns: The project id.
        """
        projects: list[Project] = await self.get_user_projects(user_id)
        if len(projects) != 1:
            raise UserException(
                f"A project_id must be provided because this user is associated with {len(projects)} projects."
            )

        return projects[0].project_id


class LdapProjectService(ProjectService):
    @abstractmethod
    def _search_user_projects(self, conn: Connection, user_id: str) -> list[Project]:
        """
        Search user's projects from LDAP.

        Args:
            conn: LDAP connection.
            user_id: The user ID.

        Returns:
            The user's projects.
        """
        pass

    @staticmethod
    def _get_connection(host: str, port: int, user: str, password: str, use_ssl: bool, timeout: int = 5) -> Connection:
        """
        Creates LDAP connection.
        """
        server = Server(host=host, port=port, use_ssl=use_ssl, connect_timeout=timeout)
        return Connection(server=server, user=user, password=password)

    @override
    async def _get_user_projects(self, user_id: str) -> list[Project]:
        """
        Return user's projects.

        Args:
            user_id: The user ID.
        """

        config = csc_ldap_config()

        host = config.CSC_LDAP_HOST
        user = config.CSC_LDAP_USER
        password = config.CSC_LDAP_PASSWORD

        parsed = urlparse(host)
        scheme = parsed.scheme.lower()

        if scheme == "ldaps":
            use_ssl = True
            port = parsed.port if parsed.port else 636  # default LDAPS port
        elif scheme == "ldap":
            use_ssl = False
            port = parsed.port if parsed.port else 389  # default LDAP port
        else:
            raise RuntimeError(f"Unsupported LDAP protocol: {scheme}")

        try:
            LOG.info("Connecting to LDAP server '%s' using port '%s' with ssl '%s'", host, port, use_ssl)

            with self._get_connection(host, port, user, password, use_ssl) as conn:
                return self._search_user_projects(conn, user_id)
        except Exception as ex:
            raise SystemException("Failed to retrieve user projects.") from ex

    @override
    async def _verify_user_project(self, user_id: str, project_id: str) -> bool:
        """
        Verify that the user has access to the given project.

        Args:
            user_id: The user ID.
            project_id: The project ID.

        Returns:
            True if the user has access to the given project.
        """
        projects = await self.get_user_projects(user_id)
        for project in projects:
            if project.project_id == project_id:
                return True
        return False


class CscProjectService(LdapProjectService):
    @override
    def _search_user_projects(self, conn: Connection, user_id: str) -> list[Project]:
        conn.search(
            search_base=CSC_LDAP_DN,
            search_filter=CSC_LDAP_FILTER.format(username=user_id),
            attributes=[CSC_LDAP_PROJECT_ATTRIBUTE],
        )

        # Get project IDs with SD Submit service profile enabled.
        projects = []
        for entry in conn.entries:
            entry_dict = json.loads(entry.entry_to_json())
            if CSC_LDAP_SERVICE_PROFILE in entry_dict["dn"]:
                for project_id in entry_dict["attributes"]["CSCPrjNum"]:
                    projects.append(Project(project_id=project_id))

        return projects


class NoProjectService(ProjectService):
    @override
    async def _verify_user_project(self, user_id: str, project_id: str) -> bool:
        """
        Verify that the user has access to the given project.

        Args:
            user_id: The user ID.
            project_id: The project ID.

        Returns:
            True if the user has access to the given project.
        """
        return user_id == project_id

    @override
    async def _get_user_projects(self, user_id: str) -> list[Project]:
        """
        Return user's projects.

        Args:
            user_id: The user ID.
        """
        return [Project(project_id=user_id)]


class NbisProjectService(NoProjectService):
    pass
