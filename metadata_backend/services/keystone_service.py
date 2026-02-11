"""Keystone service."""

from typing import Any

import httpx
from pydantic import BaseModel
from yarl import URL

from ..api.exceptions import ForbiddenUserException, NotFoundUserException, SystemException
from ..conf.keystone import keystone_config
from ..helpers.logger import LOG
from .service_handler import ServiceHandler


class KeystoneServiceHandler(ServiceHandler):
    """Keystone service."""

    class ProjectEntry(BaseModel):
        """Model for a project entry containing Keystone token."""

        id: str
        name: str
        endpoint: str
        token: str
        uid: str
        uname: str

    class EC2Credentials(BaseModel):
        """Model for EC2 credentials."""

        access: str
        secret: str

    def __init__(self) -> None:
        """Keystone service."""

        self._config = keystone_config()

        super().__init__(
            service_name="keystone",
            base_url=URL(self._config.KEYSTONE_ENDPOINT.rstrip("/")),
            healthcheck_url=URL(self._config.KEYSTONE_ENDPOINT) / "v3",
            healthcheck_callback=self.healthcheck_callback,
        )

    async def get_project_entry(self, project: str, access_token: str) -> ProjectEntry:
        """Get project entry containing project scoped token with unscoped access token provided by OIDC.

        :param project: The project ID.
        :param userinfo: The OIDC userinfo dictionary.
        :returns: The ProjectEntry containing scoped token and metadata.
        """
        # First fetch an unscoped user token from Keystone API using the keystone access token
        resp = await self._client.request(
            method="GET",
            url=f"{self.base_url}/v3/OS-FEDERATION/identity_providers/oauth2_authentication/protocols/openid/auth",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code >= 400:
            raise ForbiddenUserException("Could not log in using the provided AAI token.")
        unscoped: str = resp.headers["X-Subject-Token"]

        # Get project availability from the unscoped user token
        output_projects: dict[str, Any] = await self._request(
            method="GET",
            url=URL(f"{self.base_url}/v3/OS-FEDERATION/projects"),
            headers={
                "X-Auth-Token": unscoped,
            },
        )

        # Find matching project id from available projects
        project_id, project_name = None, None
        for item in output_projects["projects"]:
            if item["name"].removeprefix("project_") == project:
                project_id, project_name = item["id"], item["name"]
                break
        if not project_id and not project_name:
            raise NotFoundUserException(f"Project '{project}' not found for user in Keystone.")

        # Retrieve the scoped token from the Keystone API
        resp = await self._client.request(
            method="POST",
            url=f"{self.base_url}/v3/auth/tokens",
            json={
                "auth": {
                    "identity": {
                        "methods": [
                            "token",
                        ],
                        "token": {
                            "id": unscoped,
                        },
                    },
                    "scope": {"project": {"id": project_id}},
                }
            },
        )
        ret = resp.json()

        # Get the scoped token
        scoped: str = resp.headers["X-Subject-Token"]
        # Use the first available public endpoint
        endpoint = [
            list(filter(lambda i: i["interface"] == "public", i["endpoints"]))[0]
            for i in filter(lambda i: i["type"] == "object-store", ret["token"]["catalog"])
        ][0]

        # Append the scoped project with metadata
        project_entry = self.ProjectEntry(
            id=project_id,
            name=project_name,
            endpoint=endpoint["url"],
            token=scoped,
            uid=ret["token"]["user"]["id"],
            uname=ret["token"]["user"]["name"],
        )
        return project_entry

    async def get_ec2_for_project(self, project: ProjectEntry) -> EC2Credentials:
        """Retrieve the ec2 credentials using a scoped project entry.

        :param project: The project entry containing token.
        :returns: The EC2 credentials containing access and secret keys.
        """
        try:
            resp: dict[str, Any] = await self._request(
                method="POST",
                url=URL(f"{self.base_url}/v3/users/{project.uid}/credentials/OS-EC2"),
                json_data={
                    "tenant_id": project.id,
                },
                headers={
                    "X-Auth-Token": project.token,
                },
            )
            credentials = self.EC2Credentials(
                access=resp["credential"]["access"],
                secret=resp["credential"]["secret"],
            )
            return credentials
        except KeyError as e:
            LOG.exception("Missing required credential fields: %r", e)
            raise SystemException("Invalid credential response format.")

    async def delete_ec2_from_project(self, project: ProjectEntry, credentials: EC2Credentials) -> int:
        """Delete the existing ec2 credential using scoped project from entry.

        :param project: The project entry containing token.
        :param credentials: The EC2 credentials containing access and secret keys.
        :returns: The HTTP status code from Keystone on success.
        :raises: Appropriate errors on failure.
        """
        resp = await self._client.request(
            method="DELETE",
            url=f"{self.base_url}/v3/users/{project.uid}/credentials/OS-EC2/{credentials.access}",
            json={"tenant_id": project.id},
            headers={"X-Auth-Token": project.token},
        )
        LOG.debug(
            "Successfully deleted EC2 credentials for user %s (project %s). Status: %s",
            project.uid,
            project.id,
            resp.status_code,
        )
        return int(resp.status_code)  # 204 on success

    @staticmethod
    async def healthcheck_callback(response: httpx.Response) -> bool:
        content = response.json()
        version = content.get("version") or {}
        return (version.get("status") or "") == "stable"
