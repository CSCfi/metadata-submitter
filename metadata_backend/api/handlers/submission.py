"""Handle HTTP methods for server."""

import json
import re
from datetime import datetime
from math import ceil
from typing import Any

from aiohttp import web
from aiohttp.web import Request, Response
from multidict import CIMultiDict

from ...helpers.logger import LOG
from ...helpers.validator import JSONValidator
from ..auth import get_authorized_user_id
from ..models import File, Rems, SubmissionWorkflow
from ..operators.file import FileOperator
from ..resources import (
    get_file_service,
    get_mongo_client,
    get_project_service,
    get_registration_service,
    get_submission_service,
)
from .common import to_json
from .restapi import RESTAPIIntegrationHandler


class SubmissionAPIHandler(RESTAPIIntegrationHandler):
    """API Handler for submissions."""

    @staticmethod
    async def check_submission_retrievable(req: Request, submission_id: str) -> None:
        """
        Check the that user is allowed to retrieve the submission.

        :param req: The aiohttp request.
        :param submission_id: The submission id.
        """
        submission_service = get_submission_service(req)
        project_service = get_project_service(req)

        # Check that submission exists.
        await submission_service.check_submission(submission_id)

        # Check that the user owns the submission.
        user_id = get_authorized_user_id(req)
        project_id = await submission_service.get_project_id(submission_id)
        await project_service.verify_user_project(user_id, project_id)

    @staticmethod
    async def check_submission_modifiable(req: Request, submission_id: str) -> None:
        """
        Check the that user is allowed to modify the submission.

        :param req: The aiohttp request.
        :param submission_id: The submission id.
        """
        submission_service = get_submission_service(req)
        project_service = get_project_service(req)

        # Check that submission exists.
        await submission_service.check_submission(submission_id)

        # Check that the user owns the submission.
        user_id = get_authorized_user_id(req)
        project_id = await submission_service.get_project_id(submission_id)
        await project_service.verify_user_project(user_id, project_id)

        # Check that the submission has not been published.
        await submission_service.check_not_published(submission_id)

    async def get_submissions(self, req: Request) -> Response:
        """Get submissions owned by the project with pagination values. Optionally filter by submission name.

        :param req: GET Request
        :returns: Submissions owned by the project.
        """
        user_id = get_authorized_user_id(req)
        project_id = self._get_param(req, "projectId")

        project_service = get_project_service(req)
        submission_service = get_submission_service(req)

        # Check that user is affiliated with the project.
        await project_service.verify_user_project(user_id, project_id)

        page = self._get_page_param(req, "page", 1)
        page_size = self._get_page_param(req, "per_page", 5)

        def param_to_bool(param_name: str) -> bool | None:
            param_value = req.query.get(param_name)
            if param_value:
                if param_value.lower() not in {"true", "false"}:
                    raise web.HTTPBadRequest(reason=f"'{param_name}' parameter must be either 'true' or 'false'")
                return param_value.lower() == "true"
            return None

        def param_to_date(param_name: str) -> datetime | None:
            param_value = req.query.get(param_name)
            date_format = "%Y-%m-%d"
            try:
                return datetime.strptime(param_value, date_format) if param_value else None
            except ValueError:
                raise web.HTTPBadRequest(
                    reason=f"'{param_name}' parameter must be formated as {date_format}"
                ) from ValueError

        submissions, total_submissions = await submission_service.get_submissions(
            project_id,
            name=req.query.get("name"),
            is_published=param_to_bool("published"),
            created_start=param_to_date("date_created_start"),
            created_end=param_to_date("date_created_end"),
            modified_start=param_to_date("date_modified_start"),
            modified_end=param_to_date("date_modified_end"),
            page=page,
            page_size=page_size,
        )

        body = to_json(
            {
                "page": {
                    "page": page,
                    "size": page_size,
                    "totalPages": ceil(total_submissions / page_size),
                    "totalSubmissions": total_submissions,
                },
                "submissions": submissions,
            }
        )

        url = f"{req.scheme}://{req.host}{req.path}"
        link_headers = self._pagination_header_links(url, page, page_size, total_submissions)
        LOG.debug("Pagination header links: %r", link_headers)
        LOG.info(
            "Querying for project: %r submissions resulted in %d submissions.",
            project_id,
            total_submissions,
        )

        return web.Response(
            body=body,
            status=200,
            headers=link_headers,
            content_type="application/json",
        )

    async def post_submission(self, req: Request) -> Response:
        """Create new submission.

        :param req: POST request
        :returns: JSON response containing submission ID for created submission
        """
        user_id = get_authorized_user_id(req)
        project_service = get_project_service(req)
        submission_service = get_submission_service(req)

        content = await self._json_data(req)

        JSONValidator(content, "submission").validate()

        # Check that user is affiliated with the project.
        await project_service.verify_user_project(user_id, content["projectId"])

        # Check if the name of the submission is unique within the project
        existing_submission = await submission_service.get_submission_by_name(content["projectId"], content["name"])
        if existing_submission:
            reason = f"Submission with name '{content['name']}' already exists in project {content['projectId']}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        submission_id = await submission_service.add_submission(content)

        body = to_json({"submissionId": submission_id})

        url = f"{req.scheme}://{req.host}{req.path}"
        location_headers = CIMultiDict(Location=f"{url}/{submission_id}")
        LOG.info("POST new submission with ID: %r was successful.", submission_id)
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
        submission_service = get_submission_service(req)

        # Check that the submission can be retrieved by the user.
        await self.check_submission_retrievable(req, submission_id)

        submission = await submission_service.get_submission_by_id(submission_id)

        LOG.info("GET submission with ID: %r was successful.", submission_id)
        return web.Response(
            body=to_json(submission),
            status=200,
            content_type="application/json",
        )

    async def patch_submission(self, req: Request) -> Response:
        """Update submission document.

        The DOI and REMS sub-documents can be replaced but the submission repository
        prevents them from being removed.

        The submission document can be updated by the user, however, some fields
        can't be removed or changed. If the following fields are absent from the
        updated document then the existing value in the current document is preserved:
        name, description, doiInfo, rems, projectId, workflow, linkedFolder. Furthermore,
        if the following fields are changed then the existing value in the current document
        is preserved: projectId, workflow, linkedFolder.

        :param req: PATCH request
        :returns: JSON response containing submission ID for updated submission
        """
        submission_id = req.match_info["submissionId"]
        submission_service = get_submission_service(req)

        # Check that the submission can be modified by the user.
        await self.check_submission_modifiable(req, submission_id)

        # Check patch operations in request are valid
        data = await self._json_data(req)
        if not isinstance(data, dict):
            reason = "Patch submission operation should be provided as a JSON object"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        await submission_service.update_submission(submission_id, data)

        body = to_json({"submissionId": submission_id})
        LOG.info("PATCH submission with ID: %r was successful.", submission_id)
        return web.Response(body=body, status=200, content_type="application/json")

    async def delete_submission(self, req: Request) -> web.HTTPNoContent:
        """Delete object submission from database.

        :param req: DELETE request
        :returns: HTTP No Content response
        """

        submission_id = req.match_info["submissionId"]
        submission_service = get_submission_service(req)

        # Check that the submission can be modified by the user.
        await self.check_submission_modifiable(req, submission_id)

        await submission_service.delete_submission(submission_id)  # Metadata objects and files are deleted as well.

        LOG.info("DELETE submission with ID: %r was successful.", submission_id)
        return web.HTTPNoContent()

    async def patch_submission_doi(self, req: Request) -> Response:
        """Add or replace DOI information.

        :param req: PATCH request with metadata in the body
        :returns: JSON response containing submission ID for updated submission
        """
        submission_id = req.match_info["submissionId"]
        submission_service = get_submission_service(req)

        # Check that the submission can be modified by the user.
        await self.check_submission_modifiable(req, submission_id)

        data = await self._json_data(req)
        await submission_service.update_doi_info(submission_id, data)

        body = to_json({"submissionId": submission_id})
        return web.Response(body=body, status=200, content_type="application/json")

    async def patch_submission_rems(self, req: Request) -> Response:
        """Add or replace REMS information.

        REMS example:
        {
             "workflowId": 1, # DAC
             "organizationId": "CSC",
             "licenses": [1] # POLICY
        }

        :param req: PATCH request with metadata in the body
        :returns: JSON response containing submission ID for updated submission
        """
        submission_id = req.match_info["submissionId"]
        submission_service = get_submission_service(req)

        # Check that the submission can be modified by the user.
        await self.check_submission_modifiable(req, submission_id)

        data = await self._json_data(req)
        rems = Rems(**data)
        await self.check_rems_ok(rems)
        await submission_service.update_rems(submission_id, rems)

        body = to_json({"submissionId": submission_id})
        return web.Response(body=body, status=200, content_type="application/json")

    async def patch_submission_files(self, req: Request) -> Response:
        """Patch files in a submission.

        Adds new files to the submission or updates existing ones.

        :param req: PATCH request with metadata schema in the body
        :returns: HTTP No Content response
        :raises: HTTPBadRequest if there are issues with the JSON payload
        """
        submission_id = req.match_info["submissionId"]

        file_service = get_file_service(req)

        db_client = get_mongo_client(req)
        file_operator = FileOperator(db_client)

        # Check that the submission can be modified by the user.
        await self.check_submission_modifiable(req, submission_id)

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

        # Add new files.
        for file in data:
            # Ensure file exists in the project.
            file_info = await file_operator.read_file(file["accessionId"], file["version"])
            path = file_info["path"]
            if not await file_service.is_file_by_path(submission_id, path):
                # Add file as it does not exist yet.
                await file_service.add_file(File(submission_id=submission_id, path=path, bytes=file_info["bytes"]))

        LOG.info("PATCH files in submission with ID: %r was successful.", submission_id)
        return web.HTTPNoContent()

    async def patch_submission_linked_folder(self, req: Request) -> Response:
        """Add or remove a linked folder name to a submission.

        :param req: PATCH request with metadata schema in the body
        :raises: HTTP Bad Request if submission already has a linked folder
        or request has missing / invalid linkedFolder
        :returns: HTTP No Content response
        """
        submission_id = req.match_info["submissionId"]
        submission_service = get_submission_service(req)

        data: dict[str, str] = await self._json_data(req)

        # Check that the submission can be modified by the user.
        await self.check_submission_modifiable(req, submission_id)

        # Container name limitations in SD Connect
        pattern = re.compile(r"^[0-9a-zA-Z\.\-_]{3,}$")

        folder = data["linkedFolder"]
        try:
            if folder == "":
                pass
            elif pattern.match(folder):
                await submission_service.update_folder(submission_id, folder)  # Changing folder is not supported.
            else:
                reason = "Provided an invalid linkedFolder."
                LOG.error(reason)
                raise web.HTTPBadRequest(reason=reason)
        except (KeyError, TypeError) as exc:
            reason = "A linkedFolder string is required."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason) from exc

        LOG.info("PUT a linked folder in submission with ID: %r was successful.", submission_id)
        return web.HTTPNoContent()

    async def get_submission_files(self, req: Request) -> Response:
        """Get files from a submission.

        :param req: GET request
        :returns: HTTP No Content response
        """
        submission_id = req.match_info["submissionId"]

        file_service = get_file_service(req)

        # Check that the submission can be retrieved by the user.
        await self.check_submission_retrievable(req, submission_id)

        files = [file async for file in file_service.get_files(submission_id)]

        LOG.info("GET files for submission with ID: %r was successful.", submission_id)
        return web.Response(
            body=json.dumps([f.json_dump() for f in files]),
            status=200,
            content_type="application/json",
        )

    async def get_submission_registrations(self, req: Request) -> Response:
        """Get registrations from a submission.

        :param req: GET request
        :returns: HTTP No Content response
        """
        submission_id = req.match_info["submissionId"]

        registration_service = get_registration_service(req)

        # Check that the submission can be retrieved by the user.
        await self.check_submission_retrievable(req, submission_id)

        registrations = await registration_service.get_registrations(submission_id)

        LOG.info("GET files for submission with ID: %r was successful.", submission_id)
        return web.Response(
            body=json.dumps([r.json_dump() for r in registrations]),
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
        file_id = req.match_info["fileId"]

        file_service = get_file_service(req)

        # Check that the submission can be modified by the user.
        await self.check_submission_modifiable(req, submission_id)

        if (await file_service.get_file_by_id(file_id)).submission_id != submission_id:
            reason = f"File with accession id {file_id} not found in submission {submission_id}"
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

        await file_service.delete_file_by_id(file_id)

        LOG.info(
            "Removing file: %r from submission with ID: %r was successful.",
            file_id,
            submission_id,
        )
        return web.HTTPNoContent()

    async def post_data_ingestion(self, req: Request) -> web.HTTPNoContent:
        """Start the data ingestion.

        :param req: HTTP request
        """
        user_id = get_authorized_user_id(req)

        submission_id = req.match_info["submissionId"]

        submission_service = get_submission_service(req)
        file_service = get_file_service(req)

        # Check that the submission can be modified by the user.
        await self.check_submission_modifiable(req, submission_id)

        workflow = await submission_service.get_workflow(submission_id)
        if workflow == SubmissionWorkflow.SDS:
            # Use submission id as the dataset id for CSC submissions.
            dataset_id = submission_id
        else:
            raise NotImplementedError(f"Ingest is not implemented for {workflow} submissions.")

        polling_file_data = {}
        async for file in file_service.get_files(submission_id):
            # Trigger file ingestion
            await self.admin_handler.ingest_file(
                req,
                {
                    "user": user_id,
                    "submissionId": submission_id,
                    "filepath": file.path,
                    "accessionId": file.file_id,
                },
            )
            polling_file_data[file.path] = file.file_id

        LOG.info("Polling for status 'verified' in submission with ID: %r", submission_id)
        await self.start_file_polling(
            req, polling_file_data, {"user": user_id, "submissionId": submission_id}, "verified"
        )
        LOG.info("Polling for status 'ready' in submission with ID: %r", submission_id)
        await self.start_file_polling(req, polling_file_data, {"user": user_id, "submissionId": submission_id}, "ready")

        await self.admin_handler.create_dataset(
            req,
            {
                "user": user_id,
                "fileIds": list(polling_file_data.values()),
                "datasetId": dataset_id,
            },
        )

        await self.admin_handler.release_dataset(req, dataset_id)

        LOG.info("Ingesting files for submission with ID: %r was successful.", submission_id)

        return web.HTTPNoContent()
