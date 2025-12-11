"""Class for contacting Pouta Keystone service."""

import os
import time

from aiohttp import ClientTimeout, web
from aiohttp.client_exceptions import ClientConnectorError
from pydantic import BaseModel
from yarl import URL

from ..helpers.logger import LOG
from .service_handler import ServiceHandler


class KeystoneService(ServiceHandler):
    """Handler for Keystone API Calls."""

    service_name = "Keystone"

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
        """Define Keystone variables."""
        KEYSTONE_ENDPOINT = os.getenv("KEYSTONE_ENDPOINT")
        if not KEYSTONE_ENDPOINT:
            raise RuntimeError(f"{KEYSTONE_ENDPOINT} environment variable is undefined.")
        super().__init__(base_url=URL(KEYSTONE_ENDPOINT.rstrip("/")))

    async def get_project_entry(self, project: str, access_token: str) -> ProjectEntry:
        """Get project entry containing project scoped token with unscoped access token provided by OIDC.

        :param project: The project ID.
        :param userinfo: The OIDC userinfo dictionary.
        :returns: The ProjectEntry containing scoped token and metadata.
        """
        # First fetch an unscoped user token from Keystone API using the keystone access token
        async with self._client.request(
            method="GET",
            url=f"{self.base_url}/v3/OS-FEDERATION/identity_providers/oauth2_authentication/protocols/openid/auth",
            headers={"Authorization": f"Bearer {access_token}"},
        ) as resp:
            if resp.status >= 400:
                raise web.HTTPForbidden(reason="Could not log in using the provided AAI token.")
            unscoped: str = resp.headers["X-Subject-Token"]

        # Get project availability from the unscoped user token
        output_projects = await self._request(
            method="GET",
            url=f"{self.base_url}/v3/OS-FEDERATION/projects",
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
            raise web.HTTPNotFound(reason=f"Project {project} not found for user in Pouta Keystone.")

        # Retrieve the scoped token from the Keystone API
        async with self._client.request(
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
        ) as resp:
            ret = await resp.json()

            # Filter for project roles to ditch unusable projects
            # obj_role = False
            # for role in ret["token"]["roles"]:
            #     if role["name"] in ("object_store_user",):
            #         obj_role = True
            # if not obj_role:
            #     return None

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
            resp = await self._request(
                method="POST",
                url=f"{self.base_url}/v3/users/{project.uid}/credentials/OS-EC2",
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
            raise web.HTTPServerError(reason="Invalid credential response format.")

    async def delete_ec2_from_project(self, project: ProjectEntry, credentials: EC2Credentials) -> int:
        """Delete the existing ec2 credential using scoped project from entry.

        :param project: The project entry containing token.
        :param credentials: The EC2 credentials containing access and secret keys.
        :returns: The HTTP status code from Keystone on success.
        :raises: Appropriate web.HTTP* errors on failure.
        """
        async with self._client.request(
            method="DELETE",
            url=f"{self.base_url}/v3/users/{project.uid}/credentials/OS-EC2/{credentials.access}",
            json={"tenant_id": project.id},
            headers={"X-Auth-Token": project.token},
        ) as resp:
            LOG.debug(
                "Successfully deleted EC2 credentials for user %s (project %s). Status: %s",
                project.uid,
                project.id,
                resp.status,
            )
            return int(resp.status)  # 204 on success

    async def healthcheck(self) -> dict[str, str]:
        """Check Keystone service heartbeat.

        :returns: Dict with status of the keystone status
        """

        try:
            start = time.time()
            async with self._client.request(
                method="GET",
                url=f"{self.base_url}/v3",
                timeout=ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    content = await response.json()
                    status = content["version"]["status"]
                    LOG.debug("Keystone REST API response content is: %r.", content)
                    status = "Ok" if (time.time() - start) < 1000 and status == "stable" else "Degraded"
                else:
                    status = "Down"

                return {"status": status}
        except ClientConnectorError as e:
            LOG.exception("Keystone REST API is down with error: %r.", e)
            return {"status": "Down"}
        except Exception as e:
            LOG.exception("Keystone REST API status retrieval failed with: %r.", e)
            return {"status": "Error"}
