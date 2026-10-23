"""Object API handler."""

from typing import Annotated, AsyncGenerator, AsyncIterator

from fastapi import HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from starlette.datastructures import UploadFile as StarletteUploadFile

from ...api.dependencies import (
    SubmissionIdOrNamePathParam,
    SubmissionIdPathParam,
    UserDependency,
    WorkflowDependency,
)
from ...conf.deployment import deployment_config
from ...database.postgres.services.submission import UnknownSubmissionUserException
from ...helpers.logger import LOG
from ..exceptions import ForbiddenUserException, SystemException, UserException
from ..models.models import Object
from ..models.submission import Submission
from ..processors.exceptions import invalid_documents_as_user_errors
from ..processors.xml.datacite import DATACITE_OBJECT_TYPE, DATACITE_SCHEMA
from ..processors.xml.processors import XmlDocumentProcessor
from ..services.submission.submission import ObjectSubmission, ObjectSubmissionService
from ..services.workflow import XmlSubmissionWorkflowProfile, workflow_profile
from .restapi import RESTAPIHandler
from .submission import SubmissionAPIHandler

ObjectTypeFilterQueryParam = Annotated[str | None, Query(alias="objectType", description="The metadata object type")]
SchemaTypeFilterQueryParam = Annotated[str | None, Query(alias="schemaType", description="The metadata schema type")]
ObjectIdFilterQueryParam = Annotated[str | None, Query(alias="objectId", description="The metadata object ID")]
ObjectNameFilterQueryParam = Annotated[str | None, Query(alias="objectName", description="The metadata object name")]

ProjectIdQueryParam = Annotated[str, Query(alias="projectId", description="The project ID")]


class ObjectAPIHandler(RESTAPIHandler):
    """Object API handler."""

    @staticmethod
    async def get_files(request: Request) -> list[StarletteUploadFile]:
        form = await request.form()
        files = []
        for _, value in form.items():
            if isinstance(value, StarletteUploadFile):
                files.append(value)
        return files

    async def add_submission(
        self,
        request: Request,
        user: UserDependency,
        workflow: WorkflowDependency,
        project_id: ProjectIdQueryParam = None,
    ) -> Submission:
        """Create a new submission using workflow specific documents and return the submission document."""

        object_submission_service = workflow_profile(workflow).object_submission_service(self._services)
        return await self._create_submission(request, user.user_id, project_id, object_submission_service)

    async def delete_submission(
        self,
        request: Request,
        user: UserDependency,
        workflow: WorkflowDependency,
        submission_id: SubmissionIdOrNamePathParam,
        project_id: ProjectIdQueryParam = None,
    ) -> Response:
        """Delete an unpublished submission."""

        project_service = self._services.project
        submission_service = self._services.submission
        user_id = user.user_id

        if not project_id:
            project_id = await self._services.project.get_project_id(user_id)

        # Hidden parameter.
        unsafe = request.query_params.get("unsafe", "").lower() == "true"

        try:
            # Check that submission is modifiable.
            submission_id = await SubmissionAPIHandler.check_submission_modifiable(
                user_id,
                submission_id,
                submission_service,
                project_service,
                workflow=workflow,
                project_id=project_id,
                search_name=True,
                unsafe=unsafe,
            )
            await self._check_not_imported(submission_id)
            # Delete submission.
            await submission_service.delete_submission(submission_id)
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        except UnknownSubmissionUserException:
            return Response(status_code=status.HTTP_204_NO_CONTENT)

    async def is_submission(
        self,
        user: UserDependency,
        workflow: WorkflowDependency,
        submission_id: SubmissionIdOrNamePathParam,
        project_id: ProjectIdQueryParam = None,
    ) -> Response:
        """Check if the submission exists."""

        submission_service = self._services.submission
        project_service = self._services.project
        user_id = user.user_id

        if not project_id:
            project_id = await self._services.project.get_project_id(user_id)

        try:
            # Check that submission is retrievable.
            await SubmissionAPIHandler.check_submission_retrievable(
                user_id,
                submission_id,
                submission_service,
                project_service,
                workflow=workflow,
                project_id=project_id,
                search_name=True,
            )
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        except UnknownSubmissionUserException:
            return Response(status_code=status.HTTP_404_NOT_FOUND)

    async def update_submission(
        self,
        request: Request,
        user: UserDependency,
        workflow: WorkflowDependency,
        submission_id: SubmissionIdOrNamePathParam,
        project_id: ProjectIdQueryParam = None,
    ) -> Response:
        """Update a submission using workflow specific documents."""

        submission_service = self._services.submission
        project_service = self._services.project

        user_id = user.user_id

        if not project_id:
            project_id = await self._services.project.get_project_id(user_id)

        # Hidden parameter.
        unsafe = request.query_params.get("unsafe", "").lower() == "true"

        try:
            # Check that submission is modifiable.
            submission_id = await SubmissionAPIHandler.check_submission_modifiable(
                user_id,
                submission_id,
                submission_service,
                project_service,
                workflow=workflow,
                project_id=project_id,
                search_name=True,
                unsafe=unsafe,
            )
        except UnknownSubmissionUserException:
            return Response(status_code=status.HTTP_404_NOT_FOUND)

        await self._check_not_imported(submission_id)

        # Update submission.
        files = await self.get_files(request)
        objects = await ObjectAPIHandler._get_object_submission_files(files)
        object_submission_service = workflow_profile(workflow).object_submission_service(self._services)
        with invalid_documents_as_user_errors():
            await object_submission_service.update(user_id, project_id, submission_id, objects)

        return Response(status_code=status.HTTP_200_OK)

    async def import_submission(
        self,
        request: Request,
        user: UserDependency,
        workflow: WorkflowDependency,
        project_id: ProjectIdQueryParam = None,
    ) -> Submission:
        """Create a new submission from a dataset accessioned and archived outside SD Submit."""

        self._check_import_user(user.user_id)

        object_import_service = workflow_profile(workflow).object_import_service(self._services, self._handlers)
        return await self._create_submission(request, user.user_id, project_id, object_import_service)

    async def _create_submission(
        self,
        request: Request,
        user_id: str,
        project_id: str | None,
        object_submission_service: ObjectSubmissionService,
    ) -> Submission:
        """
        Create a new submission from the workflow specific documents in the request.

        :param request: The request with the documents.
        :param user_id: The user id.
        :param project_id: The project id, or None for the user's project.
        :param object_submission_service: The service that creates the submission.
        :returns: The submission document.
        """
        if not project_id:
            project_id = await self._services.project.get_project_id(user_id)

        # Verify project.
        await self._services.project.verify_user_project(user_id, project_id)

        files = await self.get_files(request)
        objects = await ObjectAPIHandler._get_object_submission_files(files)

        # Process submission.
        with invalid_documents_as_user_errors():
            return await object_submission_service.create(user_id, project_id, objects)

    async def delete_imported_submission(
        self,
        user: UserDependency,
        workflow: WorkflowDependency,
        submission_id: SubmissionIdPathParam,
    ) -> Response:
        """Delete an unpublished imported submission."""

        submission_service = self._services.submission
        user_id = user.user_id

        self._check_import_user(user_id)

        try:
            # Check that submission is modifiable.
            submission_id = await SubmissionAPIHandler.check_submission_modifiable(
                user_id, submission_id, submission_service, self._services.project, workflow=workflow
            )
            await self._check_imported(submission_id)
            # Delete submission.
            await submission_service.delete_submission(submission_id)
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        except UnknownSubmissionUserException:
            return Response(status_code=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _check_import_user(user_id: str) -> None:
        """
        Check that the user is allowed to import datasets.

        :param user_id: The user id.
        :raises ForbiddenUserException: If the user is not allowed to import datasets.
        """
        if user_id not in deployment_config().IMPORT_USERS:
            raise ForbiddenUserException("The user is not allowed to import datasets.")

    async def _check_not_imported(self, submission_id: str) -> None:
        """
        Check that the submission was not imported.

        :param submission_id: The submission id.
        :raises UserException: If the submission was imported.
        """
        if await self._services.submission.is_imported(submission_id):
            raise UserException(
                f"Submission '{submission_id}' was imported. Use the {deployment_config().API_PREFIX_V1}/import "
                "endpoints instead."
            )

    async def _check_imported(self, submission_id: str) -> None:
        """
        Check that the submission was imported.

        :param submission_id: The submission id.
        :raises UserException: If the submission was not imported.
        """
        if not await self._services.submission.is_imported(submission_id):
            raise UserException(
                f"Submission '{submission_id}' was not imported. Use the {deployment_config().API_PREFIX_V1}/submit "
                "endpoints instead."
            )

    async def list_objects(
        self,
        user: UserDependency,
        submission_id: SubmissionIdOrNamePathParam,
        project_id: ProjectIdQueryParam = None,
        object_type: ObjectTypeFilterQueryParam = None,
        schema_type: SchemaTypeFilterQueryParam = None,
    ) -> list[Object]:
        """List the metadata documents in the submission."""

        submission_service = self._services.submission
        object_service = self._services.object
        project_service = self._services.project

        # Check that the submission is retrievable.
        try:
            submission_id = await SubmissionAPIHandler.check_submission_retrievable(
                user.user_id,
                submission_id,
                submission_service,
                project_service,
                project_id=project_id,
                search_name=True,
            )
        except UnknownSubmissionUserException:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        if (schema_type is not None) and (object_type is not None):
            raise UserException("Specify either objectType or schemaType but not both.")

        # Get object types.
        submission = await submission_service.get_submission_by_id(submission_id)
        object_types = workflow_profile(submission.workflow).object_types(
            submission, object_type=object_type, schema_type=schema_type
        )

        # Get objects.
        objects = await object_service.get_objects(submission_id, object_types)
        return objects

    async def get_objects(
        self,
        user: UserDependency,
        submission_id: SubmissionIdOrNamePathParam,
        project_id: ProjectIdQueryParam = None,
        object_type: ObjectTypeFilterQueryParam = None,
        schema_type: SchemaTypeFilterQueryParam = None,
        object_id: ObjectIdFilterQueryParam = None,
        object_name: ObjectNameFilterQueryParam = None,
    ) -> StreamingResponse:
        """Get the metadata documents in the submissions."""

        submission_service = self._services.submission
        object_service = self._services.object
        project_service = self._services.project

        # Check that the submission can be retrieved by the user.
        submission_id = await SubmissionAPIHandler.check_submission_retrievable(
            user.user_id, submission_id, submission_service, project_service, project_id=project_id, search_name=True
        )
        submission = await submission_service.get_submission_by_id(submission_id)

        if not (schema_type is not None) ^ (object_type is not None):
            raise UserException("Either objectType or schemaType must be defined.")

        # The submission service has been designed to process XMLs
        # that have aliases, ids, and that reference each other.
        # DataCite XML does not meet these requirements and is
        # handled separately from these XMLs.
        is_datacite = object_type == DATACITE_OBJECT_TYPE or schema_type == DATACITE_SCHEMA

        profile = workflow_profile(submission.workflow)
        object_types = profile.object_types(submission, object_type=object_type, schema_type=schema_type)

        # TODO(improve): documents in other formats than XML.
        if not isinstance(profile, XmlSubmissionWorkflowProfile):
            raise SystemException(
                f"Workflow '{submission.workflow}' has no XML documents. Its object_types should have rejected "
                "the request."
            )
        xml_config = profile.xml_config(submission)

        async def xmls() -> AsyncIterator[str]:
            # Get objects.
            objects = await object_service.get_objects(
                submission_id, object_types, object_id=object_id, name=object_name
            )

            if object_type is not None and [object_type] != object_types:
                raise SystemException(
                    f"Expecting only '{object_type}' object type. Actual object types: '{object_types}'"
                )

            # Get documents.
            for obj in objects:
                xml = await object_service.get_document(obj.objectId)
                yield xml

        async def xml_stream() -> AsyncGenerator[bytes]:
            if is_datacite:
                async for x in xmls():
                    yield x.encode("utf-8")
            else:
                async for xml in XmlDocumentProcessor.iter_xml_document(
                    xml_config,
                    xmls(),
                    object_type=object_type,
                    schema_type=schema_type,
                ):
                    yield xml

        return StreamingResponse(
            xml_stream(),
            media_type="application/xml",
            status_code=200,
        )

    @staticmethod
    async def _get_object_submission_files(files: list[StarletteUploadFile]) -> list[ObjectSubmission]:
        """
        Get object submission files from multipart/form-data.

        :param files: files from multipart/form-data.
        :return: The object submission files.
        """

        objects = []

        for file in files:
            if file.filename:
                content = await file.read()
                try:
                    document = content.decode("utf-8")
                except UnicodeDecodeError:
                    LOG.error(f"Could not decode file '{file.filename}' as UTF-8")
                    raise UserException(f"Could not decode file '{file.filename}' as UTF-8")

                objects.append(ObjectSubmission(filename=file.filename, document=document))

        if not objects:
            raise UserException("No files in the multipart request")

        return objects
