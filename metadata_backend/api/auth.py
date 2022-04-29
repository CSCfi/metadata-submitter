"""Handle Access for request and OIDC workflow."""

import time
from typing import Dict, List, Union

from aiohttp import web
from aiohttp.web import Request, Response
from oidcrp.exception import OidcServiceError
from oidcrp.rp_handler import RPHandler

from ..helpers.logger import LOG
from .operators import ProjectOperator, UserOperator
import aiohttp_session


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
            },
        }
        self.rph = RPHandler(self.oidc_url, client_configs=self.oidc_conf)

    async def login(self, req: Request) -> Response:
        """Redirect user to AAI login.

        :param req: A HTTP request instance (unused)
        :raises: HTTPSeeOther redirect to login AAI
        :raises: HTTPInternalServerError if OIDC configuration init failed
        :returns: HTTPSseeOther redirect to AAI
        """
        LOG.debug("Start login")

        # Generate authentication payload
        session = None
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
        raise response

    async def callback(self, req: Request) -> Response:
        """Include correct tokens in cookies as a callback after login.

        Sets session information such as access_token and user_info.
        Sets encrypted cookie to identify clients.

        :raises: HTTPUnauthorized in case login failed
        :raises: HTTPBadRequest AAI sends wrong paramters
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
        session = None
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

        # User data is read from AAI /userinfo and is used to create the user model in database
        user_data = {
            "user_id": "",
            "real_name": f"{session['userinfo']['given_name']} {session['userinfo']['family_name']}",
            # projects come from AAI in this form: "project1 project2 project3"
            # if user is not affiliated to any projects the `sdSubmitProjects` key will be missing
            "projects": session["userinfo"]["sdSubmitProjects"].split(" "),
        }
        if "CSCUserName" in session["userinfo"]:
            user_data["user_id"] = session["userinfo"]["CSCUserName"]
        elif "remoteUserIdentifier" in session["userinfo"]:
            user_data["user_id"] = session["userinfo"]["remoteUserIdentifier"]
        elif "sub" in session["userinfo"]:
            user_data["user_id"] = session["userinfo"]["sub"]
        else:
            LOG.error(
                "User was authenticated, but they are missing mandatory claim CSCUserName, remoteUserIdentifier or sub."
            )
            raise web.HTTPUnauthorized(
                reason="Could not set user, missing claim CSCUserName, remoteUserIdentifier or sub."
            )

        # Process project external IDs into the database and return accession IDs back to user_data
        user_data["projects"] = await self._process_projects(req, user_data["projects"])

        browser_session = await aiohttp_session.new_session(req)
        browser_session["at"] = time.time()

        # Inject cookie to this request to let _set_user work as expected.
        browser_session["oidc_state"] = params["state"]
        browser_session["access_token"] = session["token"]

        await self._set_user(req, browser_session, user_data)

        await self._set_user(req, browser_session, user_data)
        response = web.HTTPSeeOther(f"{self.redirect}/home")

        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-Cache"
        response.headers["Expires"] = "0"
        # done like this otherwise it will not redirect properly
        response.headers["Location"] = "/home" if self.redirect == self.domain else f"{self.redirect}/home"
        return response

    async def logout(self, req: Request) -> Response:
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

        raise response

    async def _process_projects(self, req: Request, projects: List[str]) -> List[Dict[str, str]]:
        """Process project external IDs to internal accession IDs by getting IDs\
            from database and creating projects that are missing.

        :raises: HTTPBadRequest in failed to add project to database
        :param req: A HTTP request instance
        :param projects: A list of project external IDs
        :returns: A list of objects containing project accession IDs and project numbers
        """
        projects.sort()  # sort project numbers to be increasing in order
        new_project_ids: List[Dict[str, str]] = []

        db_client = req.app["db_client"]
        operator = ProjectOperator(db_client)
        for project in projects:
            project_id = await operator.create_project(project)
            project_data = {
                "projectId": project_id,  # internal ID
                "projectNumber": project,  # human friendly
            }
            new_project_ids.append(project_data)

        return new_project_ids

    async def _set_user(
        self,
        req: Request,
        browser_session: aiohttp_session.Session,
        user_data: Dict[str, Union[List[Dict[str, str]], str]],
    ) -> None:
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
