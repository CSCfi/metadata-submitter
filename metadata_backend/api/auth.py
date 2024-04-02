"""Handle Access for request and OIDC workflow."""

import time
from typing import Any, Optional

import aiohttp_session
from aiohttp import web
from aiohttp.client_exceptions import ClientConnectorError, InvalidURL
from aiohttp.web import Request, Response
from idpyoidc.client.rp_handler import RPHandler
from idpyoidc.exception import OidcMsgError
from yarl import URL

from ..conf.conf import aai_config
from ..helpers.logger import LOG
from ..services.service_handler import ServiceHandler
from .operators.project import ProjectOperator
from .operators.user import UserOperator

# Type aliases
# ProjectList is a list of projects and their origins
ProjectList = list[dict[str, str]]
# UserData contains user profile from AAI userinfo, such as name, username and projects
UserData = dict[str, ProjectList | str]


class AccessHandler:
    """Handler for user access methods."""

    def __init__(self, aai: dict[str, Any]) -> None:
        """Define AAI variables and paths.

        :param aai: dictionary with AAI specific config
        """
        self.domain = aai["domain"]
        self.redirect = aai["redirect"]
        self.client_id = aai["client_id"]
        self.client_secret = aai["client_secret"]
        self.callback_url = aai["callback_url"]
        self.oidc_url = aai["oidc_url"].rstrip("/") + "/.well-known/openid-configuration"
        self.iss = aai["oidc_url"]
        self.scope = aai["scope"]
        self.auth_method = aai["auth_method"]

        self.oidc_conf = {
            "aai": {
                "issuer": self.iss,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "client_type": "oidc",
                "redirect_uris": [self.callback_url],
                "behaviour": {
                    "response_types": self.auth_method.split(" "),
                    "scope": self.scope.split(" "),
                },
                "add_ons": {
                    # Re-activate this once we have implemented support on AAI side
                    # "dpop": {
                    #     "function": "idpyoidc.client.oauth2.add_on.dpop.add_support",
                    #     "kwargs": {
                    #         "signing_algorithms": [
                    #             "ES256",
                    #             "ES512",
                    #         ]
                    #     },
                    # },
                    "pkce": {
                        "function": "idpyoidc.client.oauth2.add_on.pkce.add_support",
                        "kwargs": {
                            "code_challenge_length": 64,
                            "code_challenge_method": "S256",
                        },
                    },
                },
            },
        }
        self.rph = RPHandler(self.oidc_url, client_configs=self.oidc_conf)

    async def login(self, _: Request) -> web.HTTPSeeOther:
        """Redirect user to AAI login.

        :raises: HTTPInternalServerError if OIDC configuration init failed
        :returns: HTTPSseeOther redirect to AAI
        """
        LOG.debug("Start login")

        # Generate authentication payload
        try:
            # this returns str even though begin mentions a dict
            rph_session_url = self.rph.begin("aai")
        except Exception as e:
            # This can be caused if config is improperly configured, and
            # idpyoidc is unable to fetch oidc configuration from the given URL
            LOG.exception("OIDC authorization request failed with: %r", e)
            raise web.HTTPInternalServerError(reason="OIDC authorization request failed.")

        # Redirect user to AAI
        response = web.HTTPSeeOther(rph_session_url)
        response.headers["Location"] = rph_session_url
        return response

    async def callback(self, req: Request) -> Response:
        """Include correct tokens in cookies as a callback after login.

        Sets session information such as access_token and user_info.
        Sets encrypted cookie to identify clients.

        :raises: HTTPUnauthorized in case login failed
        :raises: HTTPBadRequest AAI sends wrong parameters
        :raises: HTTPForbidden in case of bad session
        :param req: A HTTP request instance with callback parameters
        :returns: HTTPSeeOther redirect to home page
        """
        # Response from AAI must have the query params `state` and `code`
        if "state" in req.query and "code" in req.query:
            LOG.debug("AAI response contained the correct params.")
            params = {"state": req.query["state"], "code": req.query["code"]}
        else:
            reason = f"AAI response is missing mandatory params, received: {req.query}"
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        # Verify oidc_state and retrieve auth session
        try:
            session_info = self.rph.get_session_information(params["state"])
        except KeyError as e:
            # This exception is raised if the RPHandler doesn't have the supplied "state"
            LOG.exception("Session not initialised, failed with: %r", e)
            raise web.HTTPUnauthorized(reason="Bad user session.")

        # Place authorization_code to session for finalize step
        session_info["code"] = params["code"]

        # finalize requests id_token and access_token with code, validates them and requests userinfo data
        try:
            session = self.rph.finalize(self.iss, session_info)
        except KeyError as e:
            LOG.exception("Issuer: %s not found, failed with: %r.", session_info["iss"], e)
            raise web.HTTPBadRequest(reason="Token issuer not found.")
        except OidcMsgError as e:
            # This exception is raised if RPHandler encounters an error due to:
            # 1. "code" is wrong, so token request failed
            # 2. token validation failed
            # 3. userinfo request failed
            LOG.exception("OIDC Callback failed with: %r", e)
            raise web.HTTPUnauthorized(reason="Invalid OIDC callback.")

        # Parse data from the userinfo endpoint to create user data containing username, real name and projects/groups
        user_data: UserData = await self._create_user_data(session["userinfo"])
        projects: ProjectList = await self._get_projects_from_userinfo(session["userinfo"])

        # Process project external IDs into the database and return accession IDs back to user_data
        user_data["projects"] = await self._process_projects(req, projects)

        # Create session
        browser_session = await aiohttp_session.new_session(req)
        browser_session["at"] = time.time()
        browser_session["oidc_state"] = session["state"]
        browser_session["access_token"] = session["token"]
        await self._set_user(req, browser_session, user_data)

        # Create response
        response = web.HTTPSeeOther(f"{self.redirect}/home")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-Cache"
        response.headers["Expires"] = "0"
        # done like this otherwise it will not redirect properly
        response.headers["Location"] = "/home" if self.redirect == self.domain else f"{self.redirect}/home"
        return response

    async def logout(self, req: Request) -> web.HTTPSeeOther:
        """Log the user out by revoking tokens.

        :param req: A HTTP request instance
        :raises: HTTPUnauthorized in case logout failed
        :returns: HTTPSeeOther redirect to login page
        """
        # Revoke token at AAI
        # Implement, when revocation_endpoint is supported by AAI

        try:
            session = await aiohttp_session.get_session(req)
            session.invalidate()
        except Exception as e:
            LOG.exception("Trying to log out an invalidated session, failed with: %r", e)
            raise web.HTTPUnauthorized

        response = web.HTTPSeeOther(f"{self.redirect}/")
        response.headers["Location"] = "/" if self.redirect == self.domain else f"{self.redirect}/"
        LOG.debug("Logged out user.")

        return response

    async def _process_projects(self, req: Request, projects: ProjectList) -> ProjectList:
        """Process project external IDs to internal accession IDs by getting IDs\
            from database and creating projects that are missing.

        :raises: HTTPBadRequest in failed to add project to database
        :param req: A HTTP request instance
        :param projects: A list of project external IDs
        :returns: A list of objects containing project accession IDs and project numbers
        """
        new_project_ids: ProjectList = []

        db_client = req.app["db_client"]
        operator = ProjectOperator(db_client)
        for project in projects:
            project_id = await operator.create_project(project["project_name"])
            project_data = {
                "projectId": project_id,  # internal ID
                "projectNumber": project["project_name"],  # human friendly
                "projectOrigin": project["project_origin"],  # where this project came from: [csc | lifescience]
            }
            new_project_ids.append(project_data)

        return new_project_ids

    async def _set_user(
        self,
        req: Request,
        browser_session: aiohttp_session.Session,
        user_data: UserData,
    ) -> str:
        """Set user in current session and return user id based on result of create_user.

        :raises: HTTPBadRequest in could not get user info from AAI OIDC
        :param req: A HTTP request instance
        :param user_data: user id and given name
        :returns: None
        """
        LOG.debug("Create and set user to database")

        db_client = req.app["db_client"]
        operator = UserOperator(db_client)

        # Create user
        user_id = await operator.create_user(user_data)

        # Check if user's projects have changed
        old_user = await operator.read_user(user_id)
        if old_user["projects"] != user_data["projects"]:
            update_operation = [
                {
                    "op": "replace",
                    "path": "/projects",
                    "value": user_data["projects"],
                }
            ]
            user_id = await operator.update_user(user_id, update_operation)

        browser_session["user_info"] = user_id
        return user_id

    async def _create_user_data(self, userinfo: dict[str, Any]) -> UserData:
        """Parse user profile data from userinfo endpoint response.

        :param userinfo: dict from userinfo containing user profile
        :returns: parsed user profile data containing username and real name
        """
        # User data is read from AAI /userinfo and is used to create the user model in database
        user_data: UserData = {
            "user_id": "",
            "real_name": f"{userinfo['given_name']} {userinfo['family_name']}",
            "projects": [],
        }
        if "CSCUserName" in userinfo:
            user_data["user_id"] = userinfo["CSCUserName"]
        elif "remoteUserIdentifier" in userinfo:
            user_data["user_id"] = userinfo["remoteUserIdentifier"]
        elif "sub" in userinfo:
            user_data["user_id"] = userinfo["sub"]
        else:
            LOG.error(
                "User was authenticated, but they are missing mandatory claim CSCUserName, remoteUserIdentifier or sub."
            )
            raise web.HTTPUnauthorized(
                reason="Could not set user, missing claim CSCUserName, remoteUserIdentifier or sub."
            )

        return user_data

    async def _get_projects_from_userinfo(self, userinfo: dict[str, Any]) -> ProjectList:
        """Parse projects and groups from userinfo endpoint response.

        :param userinfo: dict from userinfo containing user profile
        :returns: parsed projects and groups and their origins
        """
        # Handle projects, they come in different formats depending on the service used.
        # Current project sources: CSC projects, LS AAI groups
        projects: ProjectList = []
        if "sdSubmitProjects" in userinfo:
            # CSC projects come in format "project1 project2"
            csc_projects = userinfo["sdSubmitProjects"].split(" ")
            for csc_project in csc_projects:
                projects.append(
                    {
                        "project_name": csc_project,
                        "project_origin": "csc",
                    }
                )
        if "eduperson_entitlement" in userinfo:
            # LS AAI groups come in format ["group1", "group2"]
            for group in userinfo["eduperson_entitlement"]:
                projects.append(
                    {
                        # remove the oidc client information, as it's not important to the user
                        "project_name": group.split("#")[0],
                        "project_origin": "lifescience",
                    }
                )

        if len(projects) == 0:
            # No project group information received, abort, as metadata-submitter
            # object hierarchy depends on a project group to act as owner for objects
            raise web.HTTPUnauthorized(reason="User is not a member of any project.")

        return projects


class AAIServiceHandler(ServiceHandler):
    """AAI handler for API Calls."""

    def __init__(self, headers: Optional[dict[str, Any]] = None) -> None:
        """Get AAI credentials from config."""
        super().__init__(
            base_url=URL(aai_config["oidc_url"].rstrip("/")),
            http_client_headers=headers,
        )

    async def _healtcheck(self) -> dict[str, str]:
        """Check AAI service hearthbeat.

        This will return a JSON with well-known OIDC endpoints.

        :returns: Dict with status of the datacite status
        """

        try:
            start = time.time()
            async with self._client.request(
                method="GET",
                url=f"{self.base_url}/.well-known/openid-configuration",
                timeout=10,
            ) as response:
                content = await response.json()
                LOG.debug("AAI REST API response content is: %r.", content)
                if response.status == 200 and "userinfo_endpoint" in content:
                    status = "Ok" if (time.time() - start) < 1000 else "Degraded"
                else:
                    status = "Down"

                return {"status": status}
        except ClientConnectorError as e:
            LOG.exception("AAI REST API is down with error: %r.", e)
            return {"status": "Down"}
        except InvalidURL as e:
            LOG.exception("AAI REST API status retrieval failed with: %r.", e)
            return {"status": "Error"}
        except web.HTTPError as e:
            LOG.exception("AAI REST API status retrieval failed with: %r.", e)
            return {"status": "Error"}
