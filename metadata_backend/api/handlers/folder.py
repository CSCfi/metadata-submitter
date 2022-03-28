"""Handle HTTP methods for server."""
import re
from datetime import date, datetime
from distutils.util import strtobool
from math import ceil
from typing import Any, Dict, Union

import ujson
from aiohttp import web
from aiohttp.web import Request, Response
from multidict import CIMultiDict

from ...conf.conf import publisher
from ...helpers.doi import DOIHandler
from ...helpers.logger import LOG
from ...helpers.validator import JSONValidator
from ..middlewares import get_session
from ..operators import FolderOperator, Operator, UserOperator, ProjectOperator
from .restapi import RESTAPIHandler


class FolderAPIHandler(RESTAPIHandler):
    """API Handler for folders."""

    def _check_patch_folder(self, patch_ops: Any) -> None:
        """Check patch operations in request are valid.

        We check that ``metadataObjects`` and ``drafts`` have ``_required_values``.
        For tags we check that the ``submissionType`` takes either ``CSV``, ``XML`` or
        ``Form`` as values.
        :param patch_ops: JSON patch request
        :raises: HTTPBadRequest if request does not fullfil one of requirements
        :raises: HTTPUnauthorized if request tries to do anything else than add or replace
        :returns: None
        """
        _required_paths = ["/name", "/description"]
        _required_values = ["schema", "accessionId"]
        _arrays = ["/metadataObjects/-", "/drafts/-", "/doiInfo"]
        _tags = re.compile("^/(metadataObjects|drafts)/[0-9]*/(tags)$")

        for op in patch_ops:
            if _tags.match(op["path"]):
                LOG.info(f"{op['op']} on tags in folder")
                if "submissionType" in op["value"].keys() and op["value"]["submissionType"] not in [
                    "XML",
                    "CSV",
                    "Form",
                ]:
                    reason = "submissionType is restricted to either 'CSV', 'XML' or 'Form' values."
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)
                pass
            else:
                if all(i not in op["path"] for i in _required_paths + _arrays):
                    reason = f"Request contains '{op['path']}' key that cannot be updated to folders."
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)
                if op["op"] in ["remove", "copy", "test", "move"]:
                    reason = f"{op['op']} on {op['path']} is not allowed."
                    LOG.error(reason)
                    raise web.HTTPUnauthorized(reason=reason)
                if op["op"] == "replace" and op["path"] in _arrays:
                    reason = f"{op['op']} on {op['path']}; replacing all objects is not allowed."
                    LOG.error(reason)
                    raise web.HTTPUnauthorized(reason=reason)
                if op["path"] in _arrays and op["path"] != "/doiInfo":
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

    async def get_folders(self, req: Request) -> Response:
        """Get a set of folders owned by the project with pagination values.

        :param req: GET Request
        :returns: JSON list of folders available for the user
        """
        page = self._get_page_param(req, "page", 1)
        per_page = self._get_page_param(req, "per_page", 5)
        project_id = self._get_param(req, "projectId")
        sort = {"date": True, "score": False}
        db_client = req.app["db_client"]

        user_operator = UserOperator(db_client)
        current_user = get_session(req)["user_info"]
        user = await user_operator.read_user(current_user)
        user_has_project = await user_operator.check_user_has_project(project_id, user["userId"])
        if not user_has_project:
            reason = f"user {user['userId']} is not affiliated with project {project_id}"
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        folder_query: Dict[str, Union[str, Dict[str, Union[str, bool, float]]]] = {"projectId": project_id}
        # Check if only published or draft folders are requestsed
        if "published" in req.query:
            pub_param = req.query.get("published", "").title()
            if pub_param in ["True", "False"]:
                folder_query["published"] = {"$eq": bool(strtobool(pub_param))}
            else:
                reason = "'published' parameter must be either 'true' or 'false'"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)

        if "name" in req.query:
            name_param = req.query.get("name", "")
            if name_param:
                folder_query["$text"] = {"$search": name_param}
            sort["score"] = True
            sort["date"] = False

        format_incoming = "%Y-%m-%d"
        format_query = "%Y-%m-%d %H:%M:%S"
        if "date_created_start" in req.query and "date_created_end" in req.query:
            date_param_start = req.query.get("date_created_start", "")
            date_param_end = req.query.get("date_created_end", "")

            if datetime.strptime(date_param_start, format_incoming) and datetime.strptime(
                date_param_end, format_incoming
            ):
                query_start = datetime.strptime(date_param_start + " 00:00:00", format_query).timestamp()
                query_end = datetime.strptime(date_param_end + " 23:59:59", format_query).timestamp()
                folder_query["dateCreated"] = {"$gte": query_start, "$lte": query_end}
            else:
                reason = f"'date_created_start' and 'date_created_end' parameters must be formated as {format_incoming}"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)

        if "name" in req.query and "date_created_start" in req.query:
            sort["score"] = True
            sort["date"] = True

        folder_operator = FolderOperator(db_client)
        folders, total_folders = await folder_operator.query_folders(folder_query, page, per_page, sort)

        result = ujson.dumps(
            {
                "page": {
                    "page": page,
                    "size": per_page,
                    "totalPages": ceil(total_folders / per_page),
                    "totalFolders": total_folders,
                },
                "folders": folders,
            },
            escape_forward_slashes=False,
        )

        url = f"{req.scheme}://{req.host}{req.path}"
        link_headers = await self._header_links(url, page, per_page, total_folders)
        LOG.debug(f"Pagination header links: {link_headers}")
        LOG.info(f"Querying for project={project_id} folders resulted in {total_folders} folders")
        return web.Response(
            body=result,
            status=200,
            headers=link_headers,
            content_type="application/json",
        )

    async def post_folder(self, req: Request) -> Response:
        """Save object folder to database.

        :param req: POST request
        :returns: JSON response containing folder ID for submitted folder
        """
        db_client = req.app["db_client"]
        content = await self._get_data(req)

        JSONValidator(content, "folders").validate

        # Check that project exists
        project_op = ProjectOperator(db_client)
        await project_op._check_project_exists(content["projectId"])

        # Check that user is affiliated with project
        user_op = UserOperator(db_client)
        current_user = get_session(req)["user_info"]
        user = await user_op.read_user(current_user)
        user_has_project = await user_op.check_user_has_project(content["projectId"], user["userId"])
        if not user_has_project:
            reason = f"user {user['userId']} is not affiliated with project {content['projectId']}"
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        operator = FolderOperator(db_client)
        folder = await operator.create_folder(content)

        body = ujson.dumps({"folderId": folder}, escape_forward_slashes=False)

        url = f"{req.scheme}://{req.host}{req.path}"
        location_headers = CIMultiDict(Location=f"{url}/{folder}")
        LOG.info(f"POST new folder with ID {folder} was successful.")
        return web.Response(body=body, status=201, headers=location_headers, content_type="application/json")

    async def get_folder(self, req: Request) -> Response:
        """Get one object folder by its folder id.

        :param req: GET request
        :raises: HTTPNotFound if folder not owned by user
        :returns: JSON response containing object folder
        """
        folder_id = req.match_info["folderId"]
        db_client = req.app["db_client"]
        operator = FolderOperator(db_client)

        await operator.check_folder_exists(folder_id)

        await self._handle_check_ownership(req, "folders", folder_id)

        folder = await operator.read_folder(folder_id)

        LOG.info(f"GET folder with ID {folder_id} was successful.")
        return web.Response(
            body=ujson.dumps(folder, escape_forward_slashes=False), status=200, content_type="application/json"
        )

    async def patch_folder(self, req: Request) -> Response:
        """Update object folder with a specific folder id.

        :param req: PATCH request
        :returns: JSON response containing folder ID for updated folder
        """
        folder_id = req.match_info["folderId"]
        db_client = req.app["db_client"]

        operator = FolderOperator(db_client)

        await operator.check_folder_exists(folder_id)

        # Check patch operations in request are valid
        patch_ops = await self._get_data(req)
        self._check_patch_folder(patch_ops)

        # Validate against folders schema if DOI is being added
        for op in patch_ops:
            if op["path"] == "/doiInfo":
                curr_folder = await operator.read_folder(folder_id)
                curr_folder["doiInfo"] = op["value"]
                JSONValidator(curr_folder, "folders").validate

        await self._handle_check_ownership(req, "folders", folder_id)

        upd_folder = await operator.update_folder(folder_id, patch_ops if isinstance(patch_ops, list) else [patch_ops])

        body = ujson.dumps({"folderId": upd_folder}, escape_forward_slashes=False)
        LOG.info(f"PATCH folder with ID {upd_folder} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def publish_folder(self, req: Request) -> Response:
        """Update object folder specifically into published state.

        :param req: PATCH request
        :returns: JSON response containing folder ID for updated folder
        """
        folder_id = req.match_info["folderId"]
        db_client = req.app["db_client"]
        operator = FolderOperator(db_client)

        await operator.check_folder_exists(folder_id)

        await self._handle_check_ownership(req, "folders", folder_id)

        folder = await operator.read_folder(folder_id)

        obj_ops = Operator(db_client)

        # Create draft DOI and delete draft objects from the folder
        doi = DOIHandler()
        doi_data = await doi.create_draft_doi()
        identifier = {"identifierType": "DOI", "doi": doi_data["fullDOI"]}

        for obj in folder["drafts"]:
            await obj_ops.delete_metadata_object(obj["schema"], obj["accessionId"])

        # Patch the folder into a published state
        patch = [
            {"op": "replace", "path": "/published", "value": True},
            {"op": "replace", "path": "/drafts", "value": []},
            {"op": "add", "path": "/datePublished", "value": int(datetime.now().timestamp())},
            {"op": "add", "path": "/extraInfo/identifier", "value": identifier},
            {"op": "add", "path": "/extraInfo/url", "value": doi_data["dataset"]},
            {"op": "add", "path": "/extraInfo/publisher", "value": publisher},
            {
                "op": "add",
                "path": "/extraInfo/types",
                "value": {
                    "ris": "DATA",
                    "bibtex": "misc",
                    "citeproc": "dataset",
                    "schemaOrg": "Dataset",
                    "resourceTypeGeneral": "Dataset",
                },
            },
            {"op": "add", "path": "/extraInfo/publicationYear", "value": date.today().year},
        ]
        new_folder = await operator.update_folder(folder_id, patch)

        body = ujson.dumps({"folderId": new_folder}, escape_forward_slashes=False)
        LOG.info(f"Patching folder with ID {new_folder} was successful.")
        return web.Response(body=body, status=200, content_type="application/json")

    async def delete_folder(self, req: Request) -> Response:
        """Delete object folder from database.

        :param req: DELETE request
        :returns: HTTP No Content response
        """
        folder_id = req.match_info["folderId"]
        db_client = req.app["db_client"]
        operator = FolderOperator(db_client)

        await operator.check_folder_exists(folder_id)
        await operator.check_folder_published(folder_id)

        await self._handle_check_ownership(req, "folders", folder_id)

        obj_ops = Operator(db_client)

        folder = await operator.read_folder(folder_id)

        for obj in folder["drafts"] + folder["metadataObjects"]:
            await obj_ops.delete_metadata_object(obj["schema"], obj["accessionId"])

        _folder_id = await operator.delete_folder(folder_id)

        LOG.info(f"DELETE folder with ID {_folder_id} was successful.")
        return web.Response(status=204)
