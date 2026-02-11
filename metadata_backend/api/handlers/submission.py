"""Submission API handler."""

from datetime import date, datetime, time
from math import ceil
from typing import Annotated, Any

from fastapi import Body, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse

from ...api.dependencies import SubmissionIdPathParam, UserDependency
from ...conf.deployment import deployment_config
from ...database.postgres.services.submission import SubmissionService
from ...helpers.logger import LOG
from ..exceptions import UserException
from ..json import to_json_dict
from ..models.models import File, Registration, SubmissionId
from ..models.submission import PaginatedSubmissions, PaginatedSubmissionsPage, Submission, SubmissionWorkflow
from ..services.project import ProjectService
from .restapi import RESTAPIHandler

SubmissionDocumentBody = Annotated[Submission, Body(description="Submission document")]
SubmissionDocumentFragmentBody = Annotated[dict[str, Any], Body(description="Submission document")]
ProjectIdQueryParam = Annotated[str | None, Query(alias="projectId", description="The project ID")]
SubmissionNameFilterQueryParam = Annotated[str | None, Query(description="Submission name")]
PublishedFilterQueryParam = Annotated[bool | None, Query(escription="Submission published status")]
CreatedDateStartFilterQueryParam = Annotated[
    date | None, Query(description="Submissions created on or after this date (YYYY-MM-DD)")
]
CreatedDateEndFilterQueryParam = Annotated[
    date | None, Query(description="Submissions created on or before this date (YYYY-MM-DD)")
]
ModifiedDateStartFilterQueryParam = Annotated[
    date | None, Query(description="Submissions modified on or after this date (YYYY-MM-DD)")
]
ModifiedDatedEndFilterQueryParam = Annotated[
    date | None, Query(description="Submissions modified on or before this date (YYYY-MM-DD)")
]
PageQueryParam = Annotated[int, Query(ge=1, description="Page number starting from 1")]
PageSizeQueryParam = Annotated[int, Query(ge=1, le=100, alias="per_page", description="Number of submissions per page")]


class SubmissionAPIHandler(RESTAPIHandler):
    """Submission API handler."""

    @staticmethod
    async def check_submission_retrievable(
        user_id: str,
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

        :param user_id: The user id.
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
        user_id: str,
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

        :param user_id: The user id.
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
                user_id,
                submission_id,
                submission_service,
                project_service,
                workflow=workflow,
                project_id=project_id,
                search_name=search_name,
            )

        submission_id = await SubmissionAPIHandler.check_submission_retrievable(
            user_id,
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

    async def list_submissions(
        self,
        request: Request,
        user: UserDependency,
        page: PageQueryParam = 1,
        page_size: PageSizeQueryParam = 5,
        project_id: ProjectIdQueryParam = None,
        name: SubmissionNameFilterQueryParam = None,
        published: PublishedFilterQueryParam = None,
        date_created_start: CreatedDateStartFilterQueryParam = None,
        date_created_end: CreatedDateEndFilterQueryParam = None,
        date_modified_start: ModifiedDateStartFilterQueryParam = None,
        date_modified_end: ModifiedDatedEndFilterQueryParam = None,
    ) -> JSONResponse:
        """List and paginate submissions."""

        user_id = user.user_id

        if not project_id:
            project_id = await self._services.project.get_project_id(user_id)

        project_service = self._services.project
        submission_service = self._services.submission

        # Check that user is affiliated with the project.
        await project_service.verify_user_project(user_id, project_id)

        submissions, total_submissions = await submission_service.get_submissions(
            project_id,
            name=name,
            is_published=published,
            created_start=datetime.combine(date_created_start, time.min) if date_created_start else None,
            created_end=datetime.combine(date_created_end, time.max) if date_created_end else None,
            modified_start=datetime.combine(date_modified_start, time.min) if date_modified_start else None,
            modified_end=datetime.combine(date_modified_end, time.max) if date_modified_end else None,
            page=page,
            page_size=page_size,
        )

        result = PaginatedSubmissions(
            page=PaginatedSubmissionsPage(
                page=page,
                size=page_size,
                totalPages=ceil(total_submissions / page_size),
                totalSubmissions=total_submissions,
            ),
            submissions=submissions.submissions,
        )

        url = f"{request.url.scheme}://{request.url.hostname}{request.url.path}"

        return JSONResponse(
            content=to_json_dict(result), headers=self._link_header(url, page, page_size, total_submissions)
        )

    @staticmethod
    def _link_header(url: str, page: int, page_size: int, total_submissions: int) -> dict[str, str] | None:
        """Create RFC 5988 Link header.

        :param url: request url
        :param page: current page
        :param page_size: page size
        :param total_submissions: total number of submissions
        :returns: JSON with query results
        """

        if total_submissions == 0:
            return None

        total_pages = ceil(total_submissions / page_size)
        links = []

        links.append(f'<{url}?page=1&per_page={page_size}>; rel="first"')

        if page > 1:
            links.append(f'<{url}?page={page - 1}&per_page={page_size}>; rel="prev"')

        if page < total_pages:
            links.append(f'<{url}?page={page + 1}&per_page={page_size}>; rel="next"')

        links.append(f'<{url}?page={total_pages}&per_page={page_size}>; rel="last"')

        return {"Link": ", ".join(links)} if links else {}

    async def create_submission(self, user: UserDependency, submission: SubmissionDocumentBody) -> SubmissionId:
        """Create a new submission given a submission document, and return the submission id."""

        user_id = user.user_id
        project_service = self._services.project
        submission_service = self._services.submission

        # Check that user is affiliated with the project.
        await project_service.verify_user_project(user_id, submission.projectId)

        # Check if the name of the submission is unique within the project
        existing_submission = await submission_service.get_submission_by_name(submission.projectId, submission.name)
        if existing_submission:
            detail = f"Submission with name '{submission.name}' already exists in project {submission.projectId}"
            LOG.error(detail)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

        submission_id = await submission_service.add_submission(submission)
        return SubmissionId(submissionId=submission_id)

    async def get_submission(
        self,
        user: UserDependency,
        submission_id: SubmissionIdPathParam,
    ) -> Submission:
        """Returns the submission document given a submission id."""

        submission_service = self._services.submission
        project_service = self._services.project

        # Check that the submission can be retrieved by the user.
        await self.check_submission_retrievable(user.user_id, submission_id, submission_service, project_service)

        submission = await submission_service.get_submission_by_id(submission_id)
        return submission

    async def update_submission(
        self,
        user: UserDependency,
        submission_id: SubmissionIdPathParam,
        submission: SubmissionDocumentFragmentBody,
    ) -> SubmissionId:
        """Update a submission document given the submission id, and return the submission id."""

        submission_service = self._services.submission
        project_service = self._services.project

        # Check that the submission can be modified by the user.
        await self.check_submission_modifiable(user.user_id, submission_id, submission_service, project_service)

        # Merge the completely or partially updated submission document to the existing one.
        await submission_service.update_submission(submission_id, submission)

        return SubmissionId(submissionId=submission_id)

    async def delete_submission(
        self,
        request: Request,
        user: UserDependency,
        submission_id: SubmissionIdPathParam,
    ) -> Response:
        """Delete a submission given the submission id."""

        submission_service = self._services.submission
        project_service = self._services.project

        # Hidden parameter.
        unsafe = request.query_params.get("unsafe", "").lower() == "true"

        # Check that the submission can be modified by the user.
        await self.check_submission_modifiable(
            user.user_id, submission_id, submission_service, project_service, unsafe=unsafe
        )

        await submission_service.delete_submission(submission_id)  # Metadata objects and files are deleted as well.

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    async def get_submission_files(
        self,
        user: UserDependency,
        submission_id: SubmissionIdPathParam,
    ) -> list[File]:
        """Returns data files associated with the submission."""

        submission_service = self._services.submission
        project_service = self._services.project
        file_service = self._services.file

        # Check that the submission can be retrieved by the user.
        await self.check_submission_retrievable(user.user_id, submission_id, submission_service, project_service)

        files = [file async for file in file_service.get_files(submission_id=submission_id)]
        return files

    async def get_registrations(
        self,
        user: UserDependency,
        submission_id: SubmissionIdPathParam,
    ) -> Registration:
        """Returns REMS and other registrations associated with the submission."""

        submission_service = self._services.submission
        project_service = self._services.project
        registration_service = self._services.registration

        # Check that the submission can be retrieved by the user.
        await self.check_submission_retrievable(user.user_id, submission_id, submission_service, project_service)

        registration = await registration_service.get_registration(submission_id)

        if not registration:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registration not found")
        return registration

    # TODO(improve): implement NeIC SDA data ingestion
    # async def post_data_ingestion(self, req: Request) -> Response:
    #     """Start the data ingestion.
    #
    #     :param req: HTTP request
    #     """
    #     user_id = get_authorized_user_id(req)
    #
    #     submission_id = req.match_info["submissionId"]
    #
    #     submission_service = self._services.submission
    #     project_service = self._services.project
    #     file_service = self._services.file
    #
    #     # Check that the submission can be modified by the user.
    #     await self.check_submission_modifiable(req, submission_id, submission_service, project_service)
    #
    #     workflow = await submission_service.get_workflow(submission_id)
    #     if workflow == SubmissionWorkflow.SD:
    #         # Use submission id as the dataset id for CSC submissions.
    #         dataset_id = submission_id
    #     else:
    #         raise NotImplementedError(f"Ingest is not implemented for {workflow} submissions.")
    #
    #     polling_file_data = {}
    #     file_ids = []
    #     async for file in file_service.get_files(submission_id=submission_id):
    #         # Trigger file ingestion
    #         await self._handlers.admin.ingest_file(
    #             req,
    #             {
    #                 "user": user_id,
    #                 "submissionId": submission_id,
    #                 "filepath": file.path,
    #                 "accessionId": file.fileId,
    #             },
    #         )
    #         polling_file_data[file.path] = file.fileId
    #         file_ids.append(file.fileId)
    #
    #     LOG.info("Polling for status 'verified' in submission with ID: %r", submission_id)
    #     await self.start_file_polling(
    #         req, polling_file_data, {"user": user_id, "submissionId": submission_id}, IngestStatus.VERIFIED
    #     )
    #     LOG.info("Polling for status 'ready' in submission with ID: %r", submission_id)
    #     await self.start_file_polling(
    #         req, polling_file_data, {"user": user_id, "submissionId": submission_id}, IngestStatus.READY
    #     )
    #
    #     await self._handlers.admin.create_dataset(
    #         req,
    #         {
    #             "user": user_id,
    #             "fileIds": file_ids,
    #             "datasetId": dataset_id,
    #         },
    #     )
    #
    #     await self._handlers.admin.release_dataset(req, dataset_id)
    #
    #     LOG.info("Ingesting files for submission with ID: %r was successful.", submission_id)
    #
    #     return Response(status_code=status.HTTP_204_NO_CONTENT)

    # async def start_file_polling(
    #         self, req: Request, files: dict[str, str], data: dict[str, str], ingest_status: IngestStatus
    # ) -> None:
    #     """Regularly poll files to see if they have required status.
    #
    #     :param req: HTTP request
    #     :param files: List of files to be polled
    #     :param data: Includes 'user' and 'submissionId'
    #     :param ingest_status: The expected file ingestion status
    #     """
    #     status_found = {f: False for f in files.keys()}
    #
    #     file_service = self._services.file
    #
    #     while True:
    #         inbox_files = await self._handlers.admin.get_user_files(req, data["user"])
    #         for inbox_file in inbox_files:
    #             if "inboxPath" not in inbox_file or "fileStatus" not in inbox_file:
    #                 reason = "'inboxPath' or 'fileStatus' are missing from file data."
    #                 LOG.error(reason)
    #                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)
    #
    #             inbox_path = inbox_file["inboxPath"]
    #
    #             if not status_found.get(inbox_path, True):
    #                 if inbox_file["fileStatus"] == ingest_status.value:
    #                     # The file status is the expected file status.
    #                     status_found[inbox_path] = True
    #                     file_id = files[inbox_path]
    #                     await file_service.update_ingest_status(file_id, ingest_status)
    #                     if ingest_status == IngestStatus.VERIFIED:
    #                         await self._handlers.admin.post_accession_id(
    #                             req,
    #                             {
    #                                 "user": data["user"],
    #                                 "filepath": inbox_path,
    #                                 "accessionId": file_id,
    #                             },
    #                         )
    #                 elif inbox_file["fileStatus"] == IngestStatus.ERROR.value:
    #                     # The file status is ERROR.
    #                     file_id = files[inbox_path]
    #                     await file_service.update_ingest_status(file_id, IngestStatus.ERROR)
    #                     reason = f"File {inbox_path} in submission {data['submissionId']} has status 'error'"
    #                     LOG.exception(reason)
    #                     raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=reason)
    #
    #
    #         success = all(status_found.values())
    #         if success:
    #             break
    #
    #         num_waiting = sum((not x for x in status_found.values()))
    #         LOG.debug(
    #             "%d files were not yet %s for submission %s", num_waiting, ingest_status.value, data["submissionId"]
    #         )
    #         await sleep(admin_config().ADMIN_POLLING_INTERVAL)
