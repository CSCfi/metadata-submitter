"""Submission API handler."""

import json
from asyncio import sleep
from datetime import datetime
from math import ceil

from aiohttp import web
from aiohttp.web import Request, Response
from multidict import CIMultiDict

from ...conf.admin import admin_config
from ...conf.deployment import deployment_config
from ...database.postgres.models import IngestStatus
from ...database.postgres.services.submission import SubmissionService
from ...helpers.logger import LOG
from ..exceptions import UserException
from ..json import to_json_dict
from ..models.submission import Submission, SubmissionWorkflow
from ..services.project import ProjectService
from .auth import get_authorized_user_id
from .restapi import RESTAPIHandler


class SubmissionAPIHandler(RESTAPIHandler):
    """Submission API handler."""

    @staticmethod
    async def check_submission_retrievable(
        req: Request,
        submission_id: str,
        submission_service: SubmissionService,
        project_service: ProjectService,
        *,
        workflow: SubmissionWorkflow | None = None,
        project_id: str | None = None,
        search_name: bool = False,
    ) -> str:
        """
        Check the that user is allowed to retrieve the submission.

        :param req: The aiohttp request.
        :param submission_id: The submission id.
        :param submission_service: The submission service.
        :param project_service: The project service.
        :param workflow: Optional workflow.
        :param project_id: Optional project id.
        :param search_name: Search also by submission name. Requires project id.
        :returns: The submission id.
        """

        # Check that submission exists.
        if search_name and project_id is not None:
            submission_id = await submission_service.check_submission_by_id_or_name(project_id, submission_id)
        else:
            await submission_service.check_submission_by_id(submission_id)

        # Check that the user owns the submission.
        user_id = get_authorized_user_id(req)
        actual_project_id = await submission_service.get_project_id(submission_id)
        await project_service.verify_user_project(user_id, actual_project_id)

        if workflow:
            # Check that the workflow matches.
            actual_workflow = await submission_service.get_workflow(submission_id)
            if workflow != actual_workflow:
                raise UserException(f"Submission belongs to a different workflow: {actual_workflow}")

        if project_id:
            # Check that the project matches.
            if project_id != actual_project_id:
                raise UserException(f"Submission belongs to a different project: '{actual_project_id}")

        return submission_id

    @staticmethod
    async def check_submission_modifiable(
        req: Request,
        submission_id: str,
        submission_service: SubmissionService,
        project_service: ProjectService,
        *,
        workflow: SubmissionWorkflow | None = None,
        project_id: str | None = None,
        search_name: bool = False,
        unsafe: bool = False,
    ) -> str:
        """
        Check the that user is allowed to modify the submission.

        :param req: The aiohttp request.
        :param submission_id: The submission id.
        :param submission_service: The submission service.
        :param project_service: The project service.
        :param workflow: Optional workflow.
        :param project_id: Optional project id.
        :param search_name: Search also by submission name. Requires project id.
        :param unsafe: Allow changes to the submission after publishing.
        :returns: The submission id.
        """
        if deployment_config().ALLOW_UNSAFE and unsafe:
            return await SubmissionAPIHandler.check_submission_retrievable(
                req,
                submission_id,
                submission_service,
                project_service,
                workflow=workflow,
                project_id=project_id,
                search_name=search_name,
            )

        submission_id = await SubmissionAPIHandler.check_submission_retrievable(
            req,
            submission_id,
            submission_service,
            project_service,
            workflow=workflow,
            project_id=project_id,
            search_name=search_name,
        )

        # Check that the submission has not been published.
        await submission_service.check_not_published(submission_id)

        return submission_id

    async def get_submissions(self, req: Request) -> Response:
        """Get submissions owned by the project with pagination values. Optionally filter by submission name.

        :param req: GET Request
        :returns: Submissions owned by the project.
        """
        user_id = get_authorized_user_id(req)
        project_id = self.get_mandatory_param(req, "projectId")

        project_service = self._services.project
        submission_service = self._services.submission

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

        result = {
            "page": {
                "page": page,
                "size": page_size,
                "totalPages": ceil(total_submissions / page_size),
                "totalSubmissions": total_submissions,
            },
            **to_json_dict(submissions),
        }

        url = f"{req.scheme}://{req.host}{req.path}"
        link_headers = self._pagination_header_links(url, page, page_size, total_submissions)
        LOG.debug("Pagination header links: %r", link_headers)
        LOG.info(
            "Querying for project: %r submissions resulted in %d submissions.",
            project_id,
            total_submissions,
        )

        return web.json_response(result, status=200, headers=link_headers)

    @staticmethod
    def _get_page_param(req: Request, name: str, default: int) -> int:
        """Get pagination query parameter.

        :param req: HTTP request
        :param name: name of the query parameter
        :param default: Default value in case query parameter is missing
        :returns: pagination parameter value
        """
        try:
            param = int(req.query.get(name, str(default)))
        except ValueError as e:
            reason = f"The '{name}' query parameter must be a number: '{req.query.get(name)}'"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason) from e
        if param < 1:
            reason = f"The '{name}' query parameter must be greater than 0: '{req.query.get(name)}'"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return param

    @staticmethod
    def _pagination_header_links(url: str, page: int, size: int, total_objects: int) -> CIMultiDict[str]:
        """Create link header for pagination.

        :param url: base url for request
        :param page: current page
        :param size: results per page
        :param total_objects: total objects to compute the total pages
        :returns: JSON with query results
        """
        total_pages = ceil(total_objects / size)
        prev_link = f'<{url}?page={page - 1}&per_page={size}>; rel="prev", ' if page > 1 else ""
        next_link = f'<{url}?page={page + 1}&per_page={size}>; rel="next", ' if page < total_pages else ""
        last_link = f'<{url}?page={total_pages}&per_page={size}>; rel="last"' if page < total_pages else ""
        comma = ", " if 1 < page < total_pages else ""
        first_link = f'<{url}?page=1&per_page={size}>; rel="first"{comma}' if page > 1 else ""
        links = f"{prev_link}{next_link}{first_link}{last_link}"
        link_headers = CIMultiDict(Link=f"{links}")
        LOG.debug("Link headers created")
        return link_headers

    async def post_submission(self, req: Request) -> Response:
        """Create new submission.

        :param req: POST request
        :returns: JSON response containing submission ID for created submission
        """
        user_id = get_authorized_user_id(req)
        project_service = self._services.project
        submission_service = self._services.submission

        submission = Submission.model_validate(await self.get_json_dict(req))

        # Check that user is affiliated with the project.
        await project_service.verify_user_project(user_id, submission.projectId)

        # Check if the name of the submission is unique within the project
        existing_submission = await submission_service.get_submission_by_name(submission.projectId, submission.name)
        if existing_submission:
            reason = f"Submission with name '{submission.name}' already exists in project {submission.projectId}"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)

        submission_id = await submission_service.add_submission(submission)

        url = f"{req.scheme}://{req.host}{req.path}"
        location_headers = CIMultiDict(Location=f"{url}/{submission_id}")
        LOG.info("POST new submission with ID: %r was successful.", submission_id)
        return web.json_response(
            {"submissionId": submission_id},
            status=201,
            headers=location_headers,
        )

    async def get_submission(self, req: Request) -> Response:
        """Get one submission object by its submission id.

        :param req: GET request
        :raises: HTTPNotFound if submission not owned by user
        :returns: JSON response containing submission object
        """
        submission_id = req.match_info["submissionId"]
        submission_service = self._services.submission
        project_service = self._services.project

        # Check that the submission can be retrieved by the user.
        await self.check_submission_retrievable(req, submission_id, submission_service, project_service)

        submission = await submission_service.get_submission_by_id(submission_id)

        LOG.info("GET submission with ID: %r was successful.", submission_id)
        return web.json_response(to_json_dict(submission))

    async def patch_submission(self, req: Request) -> Response:
        """
        Update submission document.

        Changes are merged to the existing submission document.

        :param req: PATCH request
        :returns: JSON response containing submission ID for updated submission
        """
        submission_id = req.match_info["submissionId"]
        submission_service = self._services.submission
        project_service = self._services.project

        # Check that the submission can be modified by the user.
        await self.check_submission_modifiable(req, submission_id, submission_service, project_service)

        # Merge the completely or partially updated submission document to the existing one.
        data = await self.get_json_dict(req)
        await submission_service.update_submission(submission_id, data)

        LOG.info("PATCH submission with ID: %r was successful.", submission_id)
        return web.json_response({"submissionId": submission_id})

    async def delete_submission(self, req: Request) -> web.HTTPNoContent:
        """Delete object submission from database.

        :param req: DELETE request
        :returns: HTTP No Content response
        """

        submission_id = req.match_info["submissionId"]
        submission_service = self._services.submission
        project_service = self._services.project

        unsafe = req.query.get("unsafe", "").lower() == "true"

        # Check that the submission can be modified by the user.
        await self.check_submission_modifiable(req, submission_id, submission_service, project_service, unsafe=unsafe)

        await submission_service.delete_submission(submission_id)  # Metadata objects and files are deleted as well.

        LOG.info("DELETE submission with ID: %r was successful.", submission_id)
        return web.HTTPNoContent()

    async def get_submission_files(self, req: Request) -> Response:
        """Get files from a submission.

        :param req: GET request
        :returns: HTTP No Content response
        """
        submission_id = req.match_info["submissionId"]

        submission_service = self._services.submission
        project_service = self._services.project
        file_service = self._services.file

        # Check that the submission can be retrieved by the user.
        await self.check_submission_retrievable(req, submission_id, submission_service, project_service)

        files = [file async for file in file_service.get_files(submission_id=submission_id)]

        LOG.info("GET files for submission with ID: %r was successful.", submission_id)
        return web.Response(
            body=json.dumps([to_json_dict(f) for f in files]),
            status=200,
            content_type="application/json",
        )

    async def get_registrations(self, req: Request) -> Response:
        """Get submission registrations.

        :param req: GET request
        :returns: The submission registrations.
        """
        submission_id = req.match_info["submissionId"]

        submission_service = self._services.submission
        project_service = self._services.project
        registration_service = self._services.registration

        # Check that the submission can be retrieved by the user.
        await self.check_submission_retrievable(req, submission_id, submission_service, project_service)

        registration = await registration_service.get_registration(submission_id)

        if not registration:
            return web.Response(status=404)

        return web.json_response(to_json_dict(registration))

    async def post_data_ingestion(self, req: Request) -> web.HTTPNoContent:
        """Start the data ingestion.

        :param req: HTTP request
        """
        user_id = get_authorized_user_id(req)

        submission_id = req.match_info["submissionId"]

        submission_service = self._services.submission
        project_service = self._services.project
        file_service = self._services.file

        # Check that the submission can be modified by the user.
        await self.check_submission_modifiable(req, submission_id, submission_service, project_service)

        workflow = await submission_service.get_workflow(submission_id)
        if workflow == SubmissionWorkflow.SD:
            # Use submission id as the dataset id for CSC submissions.
            dataset_id = submission_id
        else:
            raise NotImplementedError(f"Ingest is not implemented for {workflow} submissions.")

        polling_file_data = {}
        file_ids = []
        async for file in file_service.get_files(submission_id=submission_id):
            # Trigger file ingestion
            await self._handlers.admin.ingest_file(
                req,
                {
                    "user": user_id,
                    "submissionId": submission_id,
                    "filepath": file.path,
                    "accessionId": file.fileId,
                },
            )
            polling_file_data[file.path] = file.fileId
            file_ids.append(file.fileId)

        LOG.info("Polling for status 'verified' in submission with ID: %r", submission_id)
        await self.start_file_polling(
            req, polling_file_data, {"user": user_id, "submissionId": submission_id}, IngestStatus.VERIFIED
        )
        LOG.info("Polling for status 'ready' in submission with ID: %r", submission_id)
        await self.start_file_polling(
            req, polling_file_data, {"user": user_id, "submissionId": submission_id}, IngestStatus.READY
        )

        await self._handlers.admin.create_dataset(
            req,
            {
                "user": user_id,
                "fileIds": file_ids,
                "datasetId": dataset_id,
            },
        )

        await self._handlers.admin.release_dataset(req, dataset_id)

        LOG.info("Ingesting files for submission with ID: %r was successful.", submission_id)

        return web.HTTPNoContent()

    async def start_file_polling(
        self, req: Request, files: dict[str, str], data: dict[str, str], ingest_status: IngestStatus
    ) -> None:
        """Regularly poll files to see if they have required status.

        :param req: HTTP request
        :param files: List of files to be polled
        :param data: Includes 'user' and 'submissionId'
        :param ingest_status: The expected file ingestion status
        """
        status_found = {f: False for f in files.keys()}

        file_service = self._services.file

        while True:
            inbox_files = await self._handlers.admin.get_user_files(req, data["user"])
            for inbox_file in inbox_files:
                if "inboxPath" not in inbox_file or "fileStatus" not in inbox_file:
                    reason = "'inboxPath' or 'fileStatus' are missing from file data."
                    LOG.error(reason)
                    raise web.HTTPBadRequest(reason=reason)

                inbox_path = inbox_file["inboxPath"]

                if not status_found.get(inbox_path, True):
                    if inbox_file["fileStatus"] == ingest_status.value:
                        # The file status is the expected file status.
                        status_found[inbox_path] = True
                        file_id = files[inbox_path]
                        await file_service.update_ingest_status(file_id, ingest_status)
                        if ingest_status == IngestStatus.VERIFIED:
                            await self._handlers.admin.post_accession_id(
                                req,
                                {
                                    "user": data["user"],
                                    "filepath": inbox_path,
                                    "accessionId": file_id,
                                },
                            )
                    elif inbox_file["fileStatus"] == IngestStatus.ERROR.value:
                        # The file status is ERROR.
                        file_id = files[inbox_path]
                        await file_service.update_ingest_status(file_id, IngestStatus.ERROR)
                        reason = f"File {inbox_path} in submission {data['submissionId']} has status 'error'"
                        LOG.exception(reason)
                        raise web.HTTPInternalServerError(reason=reason)

            success = all(status_found.values())
            if success:
                break

            num_waiting = sum((not x for x in status_found.values()))
            LOG.debug(
                "%d files were not yet %s for submission %s", num_waiting, ingest_status.value, data["submissionId"]
            )
            await sleep(admin_config().ADMIN_POLLING_INTERVAL)
