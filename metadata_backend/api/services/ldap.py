"""CSC's LDAP service."""

import json
import os
from urllib.parse import urlparse

from cachetools import TTLCache, cached
from ldap3 import Connection, Server

from ...helpers.logger import LOG

CSC_LDAP_HOST_ENV = "CSC_LDAP_HOST"
CSC_LDAP_USER_ENV = "CSC_LDAP_USER"
CSC_LDAP_PASSWORD_ENV = "CSC_LDAP_PASSWORD"  # nosec

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
        A list of project IDs.
    """

    def _env(key: str, default_value: str | None = None) -> str:
        value = os.getenv(key, default_value)
        if value is None:
            raise RuntimeError(f"Missing required environment variable: {key}")
        return value

    host = _env(CSC_LDAP_HOST_ENV)
    user = _env(CSC_LDAP_USER_ENV)
    password = _env(CSC_LDAP_PASSWORD_ENV)

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

        server = Server(
            host=host,
            port=port,
            use_ssl=use_ssl,
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
                    projects.extend(entry_dict["attributes"]["CSCPrjNum"])

        return projects
    except Exception as ex:
        raise RuntimeError("Failed to retrieve user projects.") from ex


def verify_user_project(user_id: str, project_id: str) -> bool:
    """
    Check if the user is affiliated with the project.

    Args:
        user_id: The user ID.
        project_id: The project ID.

    Returns:
        True if the user is affiliated with the project. False otherwise.
    """
    return project_id in get_user_projects(user_id)
