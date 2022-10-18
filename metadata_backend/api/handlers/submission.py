"""Handle HTTP methods for server."""
from datetime import datetime
from distutils.util import strtobool
from math import ceil
from typing import Dict, Union

import aiohttp_session
import ujson
from aiohttp import web
from aiohttp.web import Request, Response
from multidict import CIMultiDict

from ...helpers.logger import LOG
from ...helpers.validator import JSONValidator
from ..operators.object import Operator
from ..operators.project import ProjectOperator
from ..operators.submission import SubmissionOperator
from ..operators.user import UserOperator
from ..operators.xml_object import XMLOperator
from .restapi import RESTAPIIntegrationHandler


class SubmissionAPIHandler(RESTAPIIntegrationHandler):
    """API Handler for submissions."""

    async def get_submissions(self, req: Request) -> Response:
        """Get a set of submissions owned by the project with pagination values.

        :param req: GET Request
        :returns: JSON list of submissions available for the user
        """
        session = await aiohttp_session.get_session(req)

        page = self._get_page_param(req, "page", 1)
        per_page = self._get_page_param(req, "per_page", 5)
        project_id = self._get_param(req, "projectId")
        sort = {"date": True, "score": False, "modified": False}
        db_client = req.app["db_client"]

        user_operator = UserOperator(db_client)

        current_user = session["user_info"]
        user = await user_operator.read_user(current_user)
        user_has_project = await user_operator.check_user_has_project(project_id, user["userId"])
        if not user_has_project:
            reason = f"user {user['userId']} is not affiliated with project {project_id}"
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        submission_query: Dict[str, Union[str, Dict[str, Union[str, bool, float]]]] = {"projectId": project_id}
        # Check if only published or draft submissions are requested
        if "published" in req.query:
            pub_param = req.query.get("published", "").title()
            if pub_param in {"True", "False"}:
                submission_query["published"] = {"$eq": bool(strtobool(pub_param))}
            else:
                reason = "'published' parameter must be either 'true' or 'false'"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)

        if "name" in req.query:
            name_param = req.query.get("name", "")
            if name_param:
                submission_query["$text"] = {"$search": name_param}
            sort["score"] = True
            sort["date"] = False

        format_incoming = "%Y-%m-%d"
        format_query = "%Y-%m-%d %H:%M:%S"
        if "date_created_start" in req.query or "date_created_end" in req.query:
            date_param_start = req.query.get("date_created_start", "")
            date_param_end = req.query.get("date_created_end", "")

            if datetime.strptime(date_param_start, format_incoming) and datetime.strptime(
                date_param_end, format_incoming
            ):
                query_start = datetime.strptime(date_param_start + " 00:00:00", format_query).timestamp()
                query_end = datetime.strptime(date_param_end + " 23:59:59", format_query).timestamp()
                submission_query["dateCreated"] = {"$gte": query_start, "$lte": query_end}
            else:
                reason = f"'date_created_start' and 'date_created_end' parameters must be formated as {format_incoming}"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)

        if "date_modified_start" in req.query or "date_modified_end" in req.query:
            date_param_start = req.query.get("date_modified_start", "")
            date_param_end = req.query.get("date_modified_end", "")

            if datetime.strptime(date_param_start, format_incoming) and datetime.strptime(
                date_param_end, format_incoming
            ):
                query_start = datetime.strptime(date_param_start + " 00:00:00", format_query).timestamp()
                query_end = datetime.strptime(date_param_end + " 23:59:59", format_query).timestamp()
                submission_query["lastModified"] = {"$gte": query_start, "$lte": query_end}
            else:
                reason = (
                    f"'date_modified_start' and 'date_modified_end' parameters must be formated as {format_incoming}"
                )
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)

        if "name" in req.query and "date_created_start" in req.query:
            sort["score"] = True
            sort["date"] = True

        if "name" in req.query and "date_modified_start" in req.query and "date_created_start" not in req.query:
            sort["score"] = True
            sort["modified"] = True
            sort["date"] = False

        submission_operator = SubmissionOperator(db_client)
        submissions, total_submissions = await submission_operator.query_submissions(
            submission_query, page, per_page, sort
        )

        result = ujson.dumps(
            {
                "page": {
                    "page": page,
                    "size": per_page,
                    "totalPages": ceil(total_submissions / per_page),
                    "totalSubmissions": total_submissions,
                },
                "submissions": submissions,
            },
            escape_forward_slashes=False,
        )

        url = f"{req.scheme}://{req.host}{req.path}"
        link_headers = self._header_links(url, page, per_page, total_submissions)
        LOG.debug("Pagination header links: %r", link_headers)
        LOG.info("Querying for project: %r submissions resulted in %d submissions.", project_id, total_submissions)
        return web.Response(
            body=result,
            status=200,
            headers=link_headers,
            content_type="application/json",
        )

    async def post_submission(self, req: Request) -> Response:
        """Save object submission to database.

        :param req: POST request
        :returns: JSON response containing submission ID for submitted submission
        """
        session = await aiohttp_session.get_session(req)

        db_client = req.app["db_client"]
        content = await self._get_data(req)

        JSONValidator(content, "submission").validate

        # Check that project exists
        project_op = ProjectOperator(db_client)
        await project_op.check_project_exists(content["projectId"])

        # Check that user is affiliated with project
        user_op = UserOperator(db_client)
        current_user = session["user_info"]
        user = await user_op.read_user(current_user)
        user_has_project = await user_op.check_user_has_project(content["projectId"], user["userId"])
        if not user_has_project:
            reason = f"user {user['userId']} is not affiliated with project {content['projectId']}"
            LOG.error(reason)
            raise web.HTTPUnauthorized(reason=reason)

        operator = SubmissionOperator(db_client)
        submission = await operator.create_submission(content)

        body = ujson.dumps({"submissionId": submission}, escape_forward_slashes=False)

        url = f"{req.scheme}://{req.host}{req.path}"
        location_headers = CIMultiDict(Location=f"{url}/{submission}")
        LOG.info("POST new submission with ID: %r was successful.", submission)
        return web.Response(body=body, status=201, headers=location_headers, content_type="application/json")

    async def get_submission(self, req: Request) -> Response:
        """Get one object submission by its submission id.

        :param req: GET request
        :raises: HTTPNotFound if submission not owned by user
        :returns: JSON response containing object submission
        """
        submission_id = req.match_info["submissionId"]
        db_client = req.app["db_client"]
        operator = SubmissionOperator(db_client)

        await operator.check_submission_exists(submission_id)

        await self._handle_check_ownership(req, "submission", submission_id)

        submission = await operator.read_submission(submission_id)

        LOG.info("GET submission with ID: %r was successful.", submission_id)
        return web.Response(
            body=ujson.dumps(submission, escape_forward_slashes=False), status=200, content_type="application/json"
        )

    async def patch_submission(self, req: Request) -> Response:
        """Update object submission with a specific submission id.

        Submission only allows the 'name' and 'description' values to be patched.

        :param req: PATCH request
        :returns: JSON response containing submission ID for updated submission
        """
        submission_id = req.match_info["submissionId"]
        db_client = req.app["db_client"]

        operator = SubmissionOperator(db_client)

        # Check submission exists and is not already published
        await operator.check_submission_exists(submission_id)
        await operator.check_submission_published(submission_id, req.method)

        # Check patch operations in request are valid
        data = await self._get_data(req)
        if not isinstance(data, dict):
            reason = "Patch submission operation should be provided as a JSON object"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        patch_ops = []
        for key, value in data.items():
            if key not in {"name", "description"}:
                reason = f"Patch submission operation only accept the fields 'name', or 'description'. Provided '{key}'"
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
            patch_ops.append({"op": "replace", "path": f"/{key}", "value": value})
        # we update the submission last modified date
        _now = int(datetime.now().timestamp())
        patch_ops.append({"op": "replace", "path": "/lastModified", "value": _now})

        await self._handle_check_ownership(req, "submission", submission_id)

        upd_submission = await operator.update_submission(submission_id, patch_ops)

        body = ujson.dumps({"submissionId": upd_submission}, escape_forward_slashes=False)
        LOG.info("PATCH submission with ID: %r was successful.", upd_submission)
        return web.Response(body=body, status=200, content_type="application/json")

    async def delete_submission(self, req: Request) -> web.HTTPNoContent:
        """Delete object submission from database.

        :param req: DELETE request
        :returns: HTTP No Content response
        """
        await aiohttp_session.get_session(req)

        submission_id = req.match_info["submissionId"]
        db_client = req.app["db_client"]
        operator = SubmissionOperator(db_client)

        # Check submission exists and is not already published
        await operator.check_submission_exists(submission_id)
        await operator.check_submission_published(submission_id, req.method)

        await self._handle_check_ownership(req, "submission", submission_id)

        obj_ops = Operator(db_client)
        xml_ops = XMLOperator(db_client)

        submission = await operator.read_submission(submission_id)

        for obj in submission["drafts"] + submission["metadataObjects"]:
            await obj_ops.delete_metadata_object(obj["schema"], obj["accessionId"])
            await xml_ops.delete_metadata_object(f"xml-{obj['schema']}", obj["accessionId"])

        _submission_id = await operator.delete_submission(submission_id)

        LOG.info("DELETE submission with ID: %r was successful.", _submission_id)
        return web.HTTPNoContent()

    async def put_submission_path(self, req: Request) -> Response:
        """Put or replace metadata to a submission.

        :param req: PUT request with metadata schema in the body
        :returns: HTTP No Content response
        """
        submission_id = req.match_info["submissionId"]
        db_client = req.app["db_client"]
        operator = SubmissionOperator(db_client)

        # Check submission exists and is not already published
        await operator.check_submission_exists(submission_id)
        await operator.check_submission_published(submission_id, req.method)

        await self._handle_check_ownership(req, "submission", submission_id)

        submission = await operator.read_submission(submission_id)

        data = await self._get_data(req)

        if req.path.endswith("doi"):
            schema = "doiInfo"
        elif req.path.endswith("dac"):
            schema = "dac"
            await self.check_dac_ok({"dac": data})
        else:
            raise web.HTTPNotFound(reason=f"'{req.path}' does not exist")

        submission[schema] = data
        JSONValidator(submission, "submission").validate

        op = "add"
        if schema in submission:
            op = "replace"
        patch = [
            {"op": op, "path": f"/{schema}", "value": data},
        ]
        upd_submission = await operator.update_submission(submission_id, patch)

        body = ujson.dumps({"submissionId": upd_submission}, escape_forward_slashes=False)
        LOG.info("PUT %r in submission with ID: %r was successful.", schema, submission_id)
        return web.Response(body=body, status=200, content_type="application/json")
