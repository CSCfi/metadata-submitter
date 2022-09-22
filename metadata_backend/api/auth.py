"""Handle Access for request and OIDC workflow."""

import time
from typing import Dict, List, Union

import aiohttp_session
from aiohttp import web
from aiohttp.web import Request, Response
from oidcrp.exception import OidcServiceError
from oidcrp.rp_handler import RPHandler

from ..helpers.logger import LOG
from .operators import ProjectOperator, UserOperator

# Type aliases
# ProjectList is a list of projects and their origins
ProjectList = List[Dict[str, str]]
# UserData contains user profile from AAI userinfo, such as name, username and projects
UserData = Dict[str, Union[ProjectList, str]]


class AccessHandler:
    """Handler for user access methods."""

    def __init__(self, aai: Dict) -> None:
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
                "redirect_uris": [self.callback_url],
                "behaviour": {
                    "response_types": self.auth_method.split(" "),
                    "scope": self.scope.split(" "),
                },
                "add_ons": {
                    # Re-activate this once we have implemented support on AAI side
                    # "dpop": {
                    #     "function": "oidcrp.oauth2.add_on.dpop.add_support",
                    #     "kwargs": {
                    #         "signing_algorithms": [
                    #             "ES256",
                    #             "ES512",
                    #         ]
                    #     },
                    # },
                    "pkce": {
                        "function": "oidcrp.oauth2.add_on.pkce.add_support",
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

        :param _: A HTTP request instance (unused)
        :raises: HTTPInternalServerError if OIDC configuration init failed
        :returns: HTTPSseeOther redirect to AAI
        """
        LOG.debug("Start login")

        # Generate authentication payload
        try:
            session = self.rph.begin("aai")
        except Exception as e:
            # This can be caused if config is improperly configured, and
            # oidcrp is unable to fetch oidc configuration from the given URL
            LOG.error(f"OIDC authorization request failed: {e}")
            raise web.HTTPInternalServerError(reason="OIDC authorization request failed.")

        # Redirect user to AAI
        response = web.HTTPSeeOther(session["url"])
        response.headers["Location"] = session["url"]
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
            session = self.rph.get_session_information(params["state"])
        except KeyError as e:
            # This exception is raised if the RPHandler doesn't have the supplied "state"
            LOG.error(f"Session not initialised: {e}")
            raise web.HTTPUnauthorized(reason="Bad user session.")

        # Place authorization_code to session for finalize step
        session["auth_request"]["code"] = params["code"]

        # finalize requests id_token and access_token with code, validates them and requests userinfo data
        try:
            session = self.rph.finalize(session["iss"], session["auth_request"])
        except KeyError as e:
            LOG.error(f"Issuer {session['iss']} not found: {e}.")
            raise web.HTTPBadRequest(reason="Token issuer not found.")
        except OidcServiceError as e:
            # This exception is raised if RPHandler encounters an error due to:
            # 1. "code" is wrong, so token request failed
            # 2. token validation failed
            # 3. userinfo request failed
            LOG.error(f"OIDC Callback failed with: {e}")
            raise web.HTTPUnauthorized(reason="Invalid OIDC callback.")

        # Parse data from the userinfo endpoint to create user data containing username, real name and projects/groups
        user_data: UserData = await self._create_user_data(session["userinfo"])
        projects: ProjectList = await self._get_projects_from_userinfo(session["userinfo"])

        # Process project external IDs into the database and return accession IDs back to user_data
        user_data["projects"] = await self._process_projects(req, projects)

        # Create session
        browser_session = await aiohttp_session.new_session(req)
        browser_session["at"] = time.time()
        browser_session["oidc_state"] = params["state"]
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
            LOG.info(f"Trying to log out an invalidated session: {e}")
            raise web.HTTPUnauthorized

        response = web.HTTPSeeOther(f"{self.redirect}/")
        response.headers["Location"] = "/" if self.redirect == self.domain else f"{self.redirect}/"
        LOG.debug("Logged out user ")

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
                "origin": project["origin"],  # where this project came from: [csc | lifescience]
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

    async def _create_user_data(self, userinfo: Dict) -> UserData:
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

    async def _get_projects_from_userinfo(self, userinfo: Dict) -> ProjectList:
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
                        "origin": "csc",
                    }
                )
        if "eduperson_entitlement" in userinfo:
            # LS AAI groups come in format ["group1", "group2"]
            for group in userinfo["eduperson_entitlement"]:
                projects.append(
                    {
                        # remove the oidc client information, as it's not important to the user
                        "project_name": group.split("#")[0],
                        "origin": "lifescience",
                    }
                )

        if len(projects) == 0:
            # No project group information received, abort, as metadata-submitter
            # object hierarchy depends on a project group to act as owner for objects
            raise web.HTTPUnauthorized(reason="User is not a member of any project.")

        return projects
