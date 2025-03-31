"""Handle HTTP methods for server."""

import re
from datetime import datetime
from math import ceil
from typing import Any

import aiohttp_session
import ujson
from aiohttp import web
from aiohttp.web import Request, Response
from multidict import CIMultiDict

from ...helpers.logger import LOG
from ...helpers.parser import str_to_bool
from ...helpers.validator import JSONValidator
from ..operators.file import FileOperator
from ..operators.object import ObjectOperator
from ..operators.object_xml import XMLObjectOperator
from ..operators.project import ProjectOperator
from ..operators.submission import SubmissionOperator
from ..operators.user import UserOperator
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

        submission_query: dict[str, str | dict[str, str | bool | float]] = {"projectId": project_id}
        # Check if only published or draft submissions are requested
        if "published" in req.query:
            pub_param = req.query.get("published", "").title()
            if pub_param in {"True", "False"}:
                submission_query["published"] = {"$eq": str_to_bool(pub_param)}
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
                submission_query["lastModified"] = {
                    "$gte": query_start,
                    "$lte": query_end,
                }
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
        LOG.info(
            "Querying for project: %r submissions resulted in %d submissions.",
            project_id,
            total_submissions,
        )
        return web.Response(
            body=result,
            status=200,
            headers=link_headers,
            content_type="application/json",
        )

    async def post_submission(self, req: Request) -> Response:
        """Save submission object to database.

        :param req: POST request
        :returns: JSON response containing submission ID for created submission
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

        # Check if the name of the submission is unique within the project
        operator = SubmissionOperator(db_client)
        existing_submission, _ = await operator.query_submissions(
            {"projectId": content["projectId"], "name": content["name"]}, page_num=1, page_size=1
        )
        if existing_submission:
            reason = f"Submission with name '{content['name']}' already exists in project {content['projectId']}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        submission = await operator.create_submission(content)

        body = ujson.dumps({"submissionId": submission}, escape_forward_slashes=False)

        url = f"{req.scheme}://{req.host}{req.path}"
        location_headers = CIMultiDict(Location=f"{url}/{submission}")
        LOG.info("POST new submission with ID: %r was successful.", submission)
        return web.Response(
            body=body,
            status=201,
            headers=location_headers,
            content_type="application/json",
        )

    async def get_submission(self, req: Request) -> Response:
        """Get one submission object by its submission id.

        :param req: GET request
        :raises: HTTPNotFound if submission not owned by user
        :returns: JSON response containing submission object
        """
        submission_id = req.match_info["submissionId"]
        db_client = req.app["db_client"]
        operator = SubmissionOperator(db_client)

        await operator.check_submission_exists(submission_id)

        await self._handle_check_ownership(req, "submission", submission_id)

        submission = await operator.read_submission(submission_id)

        LOG.info("GET submission with ID: %r was successful.", submission_id)
        return web.Response(
            body=ujson.dumps(submission, escape_forward_slashes=False),
            status=200,
            content_type="application/json",
        )

    async def patch_submission(self, req: Request) -> Response:
        """Update info of a specific submission object based on its submission id.

        Submission only allows the 'name' and 'description' values to be patched.

        :param req: PATCH request
        :returns: JSON response containing submission ID for updated submission
        """
        submission_id = req.match_info["submissionId"]
        db_client = req.app["db_client"]

        operator = SubmissionOperator(db_client)

        # Check submission existence, ownership and published state
        await operator.check_submission_exists(submission_id)
        await self._handle_check_ownership(req, "submission", submission_id)
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

        # Check submission existence, ownership and published state
        await operator.check_submission_exists(submission_id)
        await self._handle_check_ownership(req, "submission", submission_id)
        await operator.check_submission_published(submission_id, req.method)

        obj_ops = ObjectOperator(db_client)
        xml_ops = XMLObjectOperator(db_client)

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
        :returns: updated submission object
        """
        submission_id = req.match_info["submissionId"]
        db_client = req.app["db_client"]
        operator = SubmissionOperator(db_client)

        # Check submission existence, ownership and published state
        await operator.check_submission_exists(submission_id)
        await self._handle_check_ownership(req, "submission", submission_id)
        await operator.check_submission_published(submission_id, req.method)

        data = await self._get_data(req)

        if req.path.endswith("doi"):
            schema = "doiInfo"
        elif req.path.endswith("rems"):
            schema = "rems"
            await self.check_rems_ok({"rems": data})
        else:
            raise web.HTTPNotFound(reason=f"'{req.path}' does not exist")

        upd_submission_id = await self.update_object_in_submission(operator, submission_id, schema, data)
        body = ujson.dumps({"submissionId": upd_submission_id}, escape_forward_slashes=False)
        return web.Response(body=body, status=200, content_type="application/json")

    async def patch_submission_files(self, req: Request) -> Response:
        """Patch files in a submission.

        Adds new files to the submission or updates existing ones.

        :param req: PATCH request with metadata schema in the body
        :returns: HTTP No Content response
        :raises: HTTPBadRequest if there are issues with the JSON payload
        """
        submission_id = req.match_info["submissionId"]
        db_client = req.app["db_client"]
        submission_operator = SubmissionOperator(db_client)
        file_operator = FileOperator(db_client)

        # Check submission existence, ownership, and published state
        await submission_operator.check_submission_exists(submission_id)
        await self._handle_check_ownership(req, "submission", submission_id)
        await submission_operator.check_submission_published(submission_id, req.method)

        try:
            data: list[dict[str, Any]] = await req.json()
        except Exception as e:
            reason = f"JSON is not correctly formatted, err: {e}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

        # Validate incoming data
        if not all("accessionId" in file and "version" in file for file in data):
            reason = "Each file must contain 'accessionId' and 'version'."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        submission = await submission_operator.read_submission(submission_id)
        current_files = {file["accessionId"]: file for file in submission.get("files", [])}

        # Add/update new files with the current file list
        for file in data:
            # Ensure file exists in the project
            await file_operator.read_file(file["accessionId"], file["version"])

            # Check if objectId exists in the specified schema collection
            if "objectId" in file:
                object_id = file["objectId"]
                required_keys = {"accessionId", "schema"}
                if set(object_id.keys()) != required_keys:
                    reason = "The objectId value must contain object with only 'accessionId' and 'schema' keys."
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)

                schema = object_id["schema"]
                accession_id = object_id["accessionId"]
                if not any(
                    obj["schema"] == schema and obj["accessionId"] == accession_id
                    for obj in submission["metadataObjects"]
                ):
                    reason = (
                        f"A {schema} object with accessionId '{accession_id}' does not exist in the submission's list "
                        "of metadata objects."
                    )
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)

            if file["accessionId"] not in current_files:
                file["status"] = file.get("status", "added")  # Default status to "added" if not provided
            current_files[file["accessionId"]] = file

        # Check validity of updated files list in submission
        updated_files = list(current_files.values())
        submission["files"] = updated_files
        JSONValidator(submission, "submission").validate

        # Update the submission in the database
        await submission_operator.update_submission(
            submission_id,
            [{"op": "replace", "path": "/files", "value": updated_files}],
        )

        LOG.info("PATCH files in submission with ID: %r was successful.", submission_id)
        return web.HTTPNoContent()

    async def put_submission_linked_folder(self, req: Request) -> Response:
        """Put a linked folder name to a submission.

        :param req: PUT request with metadata schema in the body
        :raises: HTTP Bad Request if submission already has a linked folder
        or request has missing / invalid linkedFolder
        :returns: HTTP No Content response
        """
        submission_id = req.match_info["submissionId"]
        db_client = req.app["db_client"]
        operator = SubmissionOperator(db_client)
        data: dict[str, str] = await req.json()

        # Check submission existence, ownership and published state
        await operator.check_submission_exists(submission_id)
        await self._handle_check_ownership(req, "submission", submission_id)
        await operator.check_submission_published(submission_id, req.method)

        # Container name limitations in SD Connect
        pattern = re.compile(r"^[0-9a-zA-Z\.\-_]{3,}$")

        try:
            if data["linkedFolder"] == "":
                pass
            elif pattern.match(data["linkedFolder"]):
                # Check if already linked
                folder_exists = await operator.check_submission_linked_folder(submission_id)
                if folder_exists:
                    reason = f"Updating submission {submission_id} failed. It already has a linked folder."
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)
            else:
                reason = "Provided an invalid linkedFolder."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
        except (KeyError, TypeError) as exc:
            reason = "A linkedFolder string is required."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason) from exc

        update_op = [{"op": "replace", "path": "/linkedFolder", "value": data["linkedFolder"]}]
        await operator.update_submission(submission_id, update_op)
        LOG.info("PUT a linked folder in submission with ID: %r was successful.", submission_id)
        return web.HTTPNoContent()

    async def get_submission_files(self, req: Request) -> Response:
        """Get files from a submission with the version present in submission.

        :param req: GET request
        :returns: HTTP No Content response
        """
        submission_id = req.match_info["submissionId"]
        db_client = req.app["db_client"]
        submission_operator = SubmissionOperator(db_client)

        # Check submission existence, ownership and published state
        await submission_operator.check_submission_exists(submission_id)
        await self._handle_check_ownership(req, "submission", submission_id)
        await submission_operator.check_submission_published(submission_id, req.method)

        file_operator = FileOperator(db_client)

        files = await file_operator.read_submission_files(submission_id)

        LOG.info("GET files for submission with ID: %r was successful.", submission_id)
        return web.Response(
            body=ujson.dumps(files, escape_forward_slashes=False),
            status=200,
            content_type="application/json",
        )

    async def delete_submission_files(self, req: Request) -> Response:
        """Remove a file from a submission.

        :param req: DELETE request
        :raises HTTP Not Found if file not associated with submission
        :returns: HTTP No Content response
        """
        submission_id = req.match_info["submissionId"]
        file_accession_id = req.match_info["fileId"]
        db_client = req.app["db_client"]
        submission_operator = SubmissionOperator(db_client)

        # Check submission exists and is not already published
        await submission_operator.check_submission_exists(submission_id)
        await submission_operator.check_submission_published(submission_id, req.method)

        await self._handle_check_ownership(req, "submission", submission_id)

        file_operator = FileOperator(db_client)

        file_in_submission = await file_operator.check_submission_has_file(submission_id, file_accession_id)

        if not file_in_submission:
            reason = f"File with accession id {file_accession_id} not found in submission {submission_id}"
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

        await file_operator.remove_file_submission(file_accession_id, submission_id=submission_id)
        LOG.info(
            "Removing file: %r from submission with ID: %r was successful.",
            file_accession_id,
            submission_id,
        )
        return web.HTTPNoContent()

    async def post_data_ingestion(self, req: Request) -> web.HTTPNoContent:
        """Start the data ingestion.

        :param req: HTTP request
        """
        submission_id = req.match_info["submissionId"]
        data = await self._get_data(req)

        db_client = req.app["db_client"]
        submission_operator = SubmissionOperator(db_client)
        file_operator = FileOperator(db_client)

        # Check submission exists and is not already published
        await submission_operator.check_submission_exists(submission_id)
        await self._handle_check_ownership(req, "submission", submission_id)
        await submission_operator.check_submission_published(submission_id, req.method)

        try:
            username, files = data["username"], data["files"]
            if not isinstance(username, str) or not isinstance(files, list) or not username or not files:
                reason = "Invalid input: 'username' must be a string and 'files' must be a non-empty list."
                raise ValueError(reason)
        except (KeyError, ValueError) as e:
            reason = "'username' and 'files' are mandatory parameters."
            LOG.exception("%s: %s", reason, str(e))
            raise web.HTTPBadRequest(reason=reason) from e

        for file in files:
            if "path" not in file or "accessionId" not in file:
                reason = "'path' and 'accessionId' are required for file ingestion."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
            # Trigger file ingestion
            ingestedFile = await self.start_file_ingestion(
                req,
                {
                    "user": username,  # User's username in inbox
                    "submissionId": submission_id,
                    "filepath": file["path"],
                    "accessionId": file["accessionId"],
                },
                file_operator,
            )
            LOG.debug("Ingested file: %r", ingestedFile["filepath"])
        return web.HTTPNoContent()
