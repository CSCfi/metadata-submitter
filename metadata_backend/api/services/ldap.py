"""CSC's LDAP service."""

import json
import os

from aiohttp import web
from cachetools import TTLCache, cached
from ldap3 import Connection, Server

CSC_LDAP_HOST_ENV = "CSC_LDAP_HOST"
CSC_LDAP_USER_ENV = "CSC_LDAP_USER"
CSC_LDAP_PASSWORD_ENV = "CSC_LDAP_PASSWORD"  # nosec
CSC_LDAP_PORT = 636
CSC_LDAP_DN = "ou=idm,dc=csc,dc=fi"
CSC_LDAP_PROJECT_ATTRIBUTE = "CSCPrjNum"
CSC_LDAP_SERVICE_PROFILE = "SP_SD-SUBMIT"
CSC_LDAP_FILTER = "(&(objectClass=applicationProcess)(CSCSPCommonStatus=ready)(CSCUserName={username}))"

user_projects_cache: TTLCache[str, list[str]] = TTLCache(maxsize=100, ttl=60 * 60)  # 1 hour


@cached(user_projects_cache)
def get_user_projects(user_id: str) -> list[str]:
    """
    Retrieve user's project IDs from CSC LDAP with SD Submit service profile enabled. Caches the projects for 1 hour.

    Args:
        user_id: The user ID.

    Returns:
        list[str]: A list of project IDs.
    """

    def _env(key: str, default_value: str | None = None) -> str:
        value = os.getenv(key, default_value)
        if value is None:
            raise RuntimeError(f"Missing required environment variable: {key}")
        return value

    host = _env(CSC_LDAP_HOST_ENV)
    user = _env(CSC_LDAP_USER_ENV)
    password = _env(CSC_LDAP_PASSWORD_ENV)

    try:
        server = Server(
            host=host,
            port=CSC_LDAP_PORT,
            use_ssl=True,
            connect_timeout=5,
        )

        projects = []

        with Connection(server=server, user=user, password=password) as conn:
            conn.search(
                search_base=CSC_LDAP_DN,
                search_filter=CSC_LDAP_FILTER.format(username=user_id),
                attributes=[CSC_LDAP_PROJECT_ATTRIBUTE],
            )

            # Extract project IDs for projects that have the SD Submit service profile enabled.
            for entry in conn.entries:
                entry_dict = json.loads(entry.entry_to_json())
                if CSC_LDAP_SERVICE_PROFILE in entry_dict["dn"]:
                    projects.append(entry_dict["attributes"]["CSCPrjNum"][0])

        return projects
    except Exception as ex:
        raise RuntimeError("Failed to retrieve user projects.") from ex


def verify_user_project(user_id: str, project_id: str) -> None:
    """
    Check if the user is affiliated with the project.

    Args:
        user_id: The user ID.
        project_id: The project ID.
    """

    if project_id not in get_user_projects(user_id):
        reason = f"User {user_id} is not affiliated with project {project_id}"
        raise web.HTTPUnauthorized(reason=reason)
