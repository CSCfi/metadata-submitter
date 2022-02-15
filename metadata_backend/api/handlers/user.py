"""Handle HTTP methods for server."""
import re
from math import ceil
from typing import Any, Dict, Tuple

import ujson
from aiohttp import web
from aiohttp.web import Request, Response
from multidict import CIMultiDict

from ...conf.conf import aai_config
from ...helpers.logger import LOG
from .restapi import RESTAPIHandler
from ..middlewares import decrypt_cookie, get_session
from ..operators import FolderOperator, Operator, UserOperator


class UserAPIHandler(RESTAPIHandler):
    """API Handler for users."""

    def _check_patch_user(self, patch_ops: Any) -> None:
        """Check patch operations in request are valid.

        We check that ``folders`` have string values (one or a list)
        and ``drafts`` have ``_required_values``.
        For tags we check that the ``submissionType`` takes either ``XML`` or
        ``Form`` as values.
        :param patch_ops: JSON patch request
        :raises: HTTPBadRequest if request does not fullfil one of requirements
        :raises: HTTPUnauthorized if request tries to do anything else than add or replace
        :returns: None
        """
        _arrays = ["/templates/-", "/folders/-"]
        _required_values = ["schema", "accessionId"]
        _tags = re.compile("^/(templates)/[0-9]*/(tags)$")
        for op in patch_ops:
            if _tags.match(op["path"]):
                LOG.info(f"{op['op']} on tags in folder")
                if "submissionType" in op["value"].keys() and op["value"]["submissionType"] not in ["XML", "Form"]:
                    reason = "submissionType is restricted to either 'XML' or 'Form' values."
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)
                pass
            else:
                if all(i not in op["path"] for i in _arrays):
                    reason = f"Request contains '{op['path']}' key that cannot be updated to user object"
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)
                if op["op"] in ["remove", "copy", "test", "move", "replace"]:
                    reason = f"{op['op']} on {op['path']} is not allowed."
                    LOG.error(reason)
                    raise web.HTTPUnauthorized(reason=reason)
                if op["path"] == "/folders/-":
                    if not (isinstance(op["value"], str) or isinstance(op["value"], list)):
                        reason = "We only accept string folder IDs."
                        LOG.error(reason)
                        raise web.HTTPBadRequest(reason=reason)
                if op["path"] == "/templates/-":
                    _ops = op["value"] if isinstance(op["value"], list) else [op["value"]]
                    for item in _ops:
                        if not all(key in item.keys() for key in _required_values):
                            reason = "accessionId and schema are required fields."
                            LOG.error(reason)
                            raise web.HTTPBadRequest(reason=reason)
                        if (
                            "tags" in item
                            and "submissionType" in item["tags"]
                            and item["tags"]["submissionType"] not in ["XML", "Form"]
                        ):
                            reason = "submissionType is restricted to either 'XML' or 'Form' values."
                            LOG.error(reason)
                            raise web.HTTPBadRequest(reason=reason)

    async def get_user(self, req: Request) -> Response:
        """Get one user by its user ID.

        :param req: GET request
        :raises: HTTPUnauthorized if not current user
        :returns: JSON response containing user object or list of user templates or user folders by id
        """
        user_id = req.match_info["userId"]
        if user_id != "current":
            LOG.info(f"User ID {user_id} was requested")
            raise web.HTTPUnauthorized(reason="Only current user retrieval is allowed")

        current_user = get_session(req)["user_info"]

        item_type = req.query.get("items", "").lower()
        if item_type:
            # Return only list of templates or list of folder IDs owned by the user
            result, link_headers = await self._get_user_items(req, current_user, item_type)
            return web.Response(
                body=ujson.dumps(result, escape_forward_slashes=False),
                status=200,
                headers=link_headers,
                content_type="application/json",
            )
        else:
            # Return whole user object if templates or folders are not specified in query
            db_client = req.app["db_client"]
            operator = UserOperator(db_client)
            user = await operator.read_user(current_user)
            LOG.info(f"GET user with ID {user_id} was successful.")
            return web.Response(
                body=ujson.dumps(user, escape_forward_slashes=False), status=200, content_type="application/json"
            )

    async def patch_user(self, req: Request) -> Response:
        """Update user object with a specific user ID.

        :param req: PATCH request
        :raises: HTTPUnauthorized if not current user
        :returns: JSON response containing user ID for updated user object
        """
        user_id = req.match_info["userId"]
        if user_id != "current":
            LOG.info(f"User ID {user_id} patch was requested")
            raise web.HTTPUnauthorized(reason="Only current user operations are allowed")
        db_client = req.app["db_client"]

        patch_ops = await self._get_data(req)
        self._check_patch_user(patch_ops)

        operator = UserOperator(db_client)

        current_user = get_session(req)["user_info"]
        user = await operator.update_user(current_user, patch_ops if isinstance(patch_ops, list) else [patch_ops])

        body = ujson.dumps({"userId": user})
        LOG.info(f"PATCH user with ID {user} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def delete_user(self, req: Request) -> Response:
        """Delete user from database.

        :param req: DELETE request
        :raises: HTTPUnauthorized if not current user
        :returns: HTTPNoContent response
        """
        user_id = req.match_info["userId"]
        if user_id != "current":
            LOG.info(f"User ID {user_id} delete was requested")
            raise web.HTTPUnauthorized(reason="Only current user deletion is allowed")
        db_client = req.app["db_client"]
        operator = UserOperator(db_client)
        fold_ops = FolderOperator(db_client)
        obj_ops = Operator(db_client)

        current_user = get_session(req)["user_info"]
        user = await operator.read_user(current_user)

        for folder_id in user["folders"]:
            _folder = await fold_ops.read_folder(folder_id)
            if "published" in _folder and not _folder["published"]:
                for obj in _folder["drafts"] + _folder["metadataObjects"]:
                    await obj_ops.delete_metadata_object(obj["schema"], obj["accessionId"])
                await fold_ops.delete_folder(folder_id)

        for tmpl in user["templates"]:
            await obj_ops.delete_metadata_object(tmpl["schema"], tmpl["accessionId"])

        await operator.delete_user(current_user)
        LOG.info(f"DELETE user with ID {current_user} was successful.")

        cookie = decrypt_cookie(req)

        try:
            req.app["Session"].pop(cookie["id"])
            req.app["Cookies"].remove(cookie["id"])
        except KeyError:
            pass

        response = web.HTTPSeeOther(f"{aai_config['redirect']}/")
        response.headers["Location"] = (
            "/" if aai_config["redirect"] == aai_config["domain"] else f"{aai_config['redirect']}/"
        )
        LOG.debug("Logged out user ")
        raise response

    async def _get_user_items(self, req: Request, user: Dict, item_type: str) -> Tuple[Dict, CIMultiDict[str]]:
        """Get draft templates owned by the user with pagination values.

        :param req: GET request
        :param user: User object
        :param item_type: Name of the items ("templates" or "folders")
        :raises: HTTPUnauthorized if not current user
        :returns: Paginated list of user draft templates and link header
        """
        # Check item_type parameter is not faulty
        if item_type not in ["templates", "folders"]:
            reason = f"{item_type} is a faulty item parameter. Should be either folders or templates"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        page = self._get_page_param(req, "page", 1)
        per_page = self._get_page_param(req, "per_page", 5)

        db_client = req.app["db_client"]
        operator = UserOperator(db_client)
        user_id = req.match_info["userId"]

        query = {"userId": user}

        items, total_items = await operator.filter_user(query, item_type, page, per_page)
        LOG.info(f"GET user with ID {user_id} was successful.")

        result = {
            "page": {
                "page": page,
                "size": per_page,
                "totalPages": ceil(total_items / per_page),
                "total" + item_type.title(): total_items,
            },
            item_type: items,
        }

        url = f"{req.scheme}://{req.host}{req.path}"
        link_headers = self._header_links(url, page, per_page, total_items)
        LOG.debug(f"Pagination header links: {link_headers}")
        LOG.info(f"Querying for user's {item_type} resulted in {total_items} {item_type}")
        return result, link_headers
