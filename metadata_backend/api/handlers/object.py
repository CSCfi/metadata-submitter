"""Object API handler."""

from typing import Annotated, AsyncGenerator, AsyncIterator, Sequence

from fastapi import HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from starlette.datastructures import UploadFile as StarletteUploadFile

from ...api.dependencies import (
    SubmissionIdOrNamePathParam,
    UserDependency,
    WorkflowDependency,
)
from ...database.postgres.services.submission import UnknownSubmissionUserException
from ..exceptions import SystemException, UserException
from ..models.models import Object
from ..models.submission import Submission, SubmissionWorkflow
from ..processors.xml.bigpicture import BP_FULL_SUBMISSION_XML_OBJECT_CONFIG
from ..processors.xml.fega import FEGA_FULL_SUBMISSION_XML_OBJECT_CONFIG
from ..processors.xml.models import XmlObjectConfig
from ..processors.xml.processors import XmlDocumentProcessor
from ..services.submission.bigpicture import BigPictureObjectSubmissionService
from ..services.submission.sensitive_data import SensitiveDataObjectSubmissionService
from ..services.submission.submission import ObjectSubmission, ObjectSubmissionService
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

        project_service = self._services.project
        user_id = user.user_id

        if not project_id:
            project_id = await self._services.project.get_project_id(user_id)

        # Verify project.
        await project_service.verify_user_project(user_id, project_id)

        files = await self.get_files(request)
        objects = await ObjectAPIHandler._get_object_submission_files(files)

        # Process submission.
        object_submission_service = await self._get_object_submission_service(workflow)
        submission = await object_submission_service.create(user_id, project_id, objects)

        return submission

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

        # Update submission.
        files = await self.get_files(request)
        objects = await ObjectAPIHandler._get_object_submission_files(files)
        object_submission_service = await self._get_object_submission_service(workflow)
        await object_submission_service.update(user_id, project_id, submission_id, objects)

        return Response(status_code=status.HTTP_200_OK)

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

        # Get workflow and project id from the submission.
        workflow = await submission_service.get_workflow(submission_id)

        if workflow == SubmissionWorkflow.BP:
            xml_config = BP_FULL_SUBMISSION_XML_OBJECT_CONFIG
        elif workflow == SubmissionWorkflow.FEGA:
            xml_config = FEGA_FULL_SUBMISSION_XML_OBJECT_CONFIG
        else:
            raise UserException(f"Unsupported workflow: {workflow.value}")

        if (schema_type is not None) and (object_type is not None):
            raise UserException("Specify either objectType or schemaType but not both.")

        # Get object types.
        object_types = self._get_xml_object_types(xml_config, object_type, schema_type)

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
        # Get workflow and project id from the submission.
        workflow = await submission_service.get_workflow(submission_id)

        if workflow == SubmissionWorkflow.BP:
            xml_config = BP_FULL_SUBMISSION_XML_OBJECT_CONFIG
        elif workflow == SubmissionWorkflow.FEGA:
            xml_config = FEGA_FULL_SUBMISSION_XML_OBJECT_CONFIG
        else:
            raise UserException(f"Unsupported workflow: {workflow.value}")

        if not (schema_type is not None) ^ (object_type is not None):
            raise UserException("Either objectType or schemaType must be defined.")

        async def xmls() -> AsyncIterator[str]:
            # Get object types.
            object_types = self._get_xml_object_types(xml_config, object_type, schema_type)

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
                xml = await object_service.get_xml_document(obj.objectId)
                yield xml

        async def xml_stream() -> AsyncGenerator[bytes]:
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
                    raise UserException(f"Could not decode file '{file.filename}' as UTF-8")

                objects.append(ObjectSubmission(filename=file.filename, document=document))

        if not objects:
            raise UserException("No files in the multipart request")

        return objects

    async def _get_object_submission_service(self, workflow: SubmissionWorkflow) -> ObjectSubmissionService:
        """
        Get object submission service.

        :param workflow: The submission workflow.
        :return: The object submission service.
        """
        project_service = self._services.project
        submission_service = self._services.submission
        object_service = self._services.object
        file_service = self._services.file

        if workflow == SubmissionWorkflow.SD:
            return SensitiveDataObjectSubmissionService(
                project_service, submission_service, object_service, file_service
            )
        elif workflow == SubmissionWorkflow.BP:
            return BigPictureObjectSubmissionService(project_service, submission_service, object_service, file_service)
        else:
            raise UserException(f"Unsupported workflow: {workflow.value}")

    @staticmethod
    def _get_xml_object_types(
        config: XmlObjectConfig, object_type: str | None = None, schema_type: str | None = None
    ) -> Sequence[str] | None:
        """
        Get XML metadata object types.

        :param config: The XML processor configuration.
        :param object_type: The object type.
        :param schema_type: The schema type.

        :returns: The XML metadata object types.
        """
        if object_type is not None:
            return [object_type]
        if schema_type is not None:
            return config.get_object_types(schema_type)
        return None
