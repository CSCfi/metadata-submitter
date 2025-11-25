"""HTTP handler for object related requests."""

from dataclasses import dataclass
from typing import AsyncIterator, Sequence, cast

from aiohttp import BodyPartReader, web
from aiohttp.web import Request, Response

from ...database.postgres.services.submission import UnknownSubmissionUserException
from ..auth import get_authorized_user_id
from ..exceptions import SystemException, UserException
from ..json import to_json_dict
from ..models.models import Objects, Project
from ..models.submission import SubmissionWorkflow
from ..processors.xml.configs import BP_FULL_SUBMISSION_XML_OBJECT_CONFIG, FEGA_FULL_SUBMISSION_XML_OBJECT_CONFIG
from ..processors.xml.models import XmlObjectConfig
from ..processors.xml.processors import XmlDocumentProcessor
from ..resources import (
    get_file_service,
    get_object_service,
    get_project_service,
    get_session_factory,
    get_submission_service,
)
from ..services.project import ProjectService
from ..services.submission.bigpicture import BigPictureObjectSubmissionService
from ..services.submission.sensitive_data import SensitiveDataObjectSubmissionService
from ..services.submission.submission import ObjectSubmission, ObjectSubmissionService
from .restapi import RESTAPIIntegrationHandler
from .submission import SubmissionAPIHandler


@dataclass(frozen=True)
class SubmissionConfig:
    """Service configuration for submitting metadata objects."""

    add_submission_workflows: tuple[SubmissionWorkflow, ...] = (
        SubmissionWorkflow.SD,
        SubmissionWorkflow.BP,
    )
    delete_submission_workflows: tuple[SubmissionWorkflow, ...] = tuple(SubmissionWorkflow)
    is_submission_workflows: tuple[SubmissionWorkflow, ...] = tuple(SubmissionWorkflow)
    update_submission_workflows: tuple[SubmissionWorkflow, ...] = (
        SubmissionWorkflow.SD,
        SubmissionWorkflow.BP,
    )
    list_objects_workflows: tuple[SubmissionWorkflow, ...] = (
        SubmissionWorkflow.BP,
        SubmissionWorkflow.FEGA,
    )
    get_objects_workflows: tuple[SubmissionWorkflow, ...] = (
        SubmissionWorkflow.BP,
        SubmissionWorkflow.FEGA,
    )


SUBMISSION_CONFIG = SubmissionConfig()


class ObjectAPIHandler(RESTAPIIntegrationHandler):
    """API Handler for Objects."""

    @staticmethod
    async def _get_project_id(user_id: str, project_service: ProjectService) -> str:
        """
        Returns a single project id associated with the user. Raises an UserException if
        the user is not associated with a single project.

        :param user_id: The user id
        :param req: HTTP request
        :returns: The project id.
        """
        projects: list[Project] = await project_service.get_user_projects(user_id)
        if len(projects) != 1:
            raise UserException(
                f"A project_id must be provided because this user is associated with {len(projects)} projects."
            )

        return projects[0].project_id

    @staticmethod
    async def add_submission(req: Request) -> Response:
        """
        Create a submission given workflow specific documents and return the submission document.

        :param req: POST multipart/form-data request
        :returns: The submission document.
        """
        project_service = get_project_service(req)
        user_id = get_authorized_user_id(req)

        workflow_name = req.match_info["workflow"]

        project_id = req.query.get("projectId")
        if not project_id:
            project_id = await ObjectAPIHandler._get_project_id(user_id, project_service)

        workflow = SubmissionWorkflow(workflow_name)
        if workflow not in SUBMISSION_CONFIG.add_submission_workflows:
            raise UserException(f"Unsupported workflow: {workflow.value}")

        # Verify project.
        await project_service.verify_user_project(user_id, project_id)

        objects = await ObjectAPIHandler._get_object_submission_files(req, workflow)

        # Process submission.
        object_submission_service = await ObjectAPIHandler._get_object_submission_service(req, workflow)
        submission = await object_submission_service.create(user_id, project_id, objects)

        return web.json_response(to_json_dict(submission))

    @staticmethod
    async def delete_submission(req: Request) -> Response:
        """
        Delete a submission given submission id or name.

        :param req: HTTP request
        """
        project_service = get_project_service(req)
        submission_service = get_submission_service(req)
        user_id = get_authorized_user_id(req)

        workflow_name = req.match_info["workflow"]
        submission_id = req.match_info["submissionId"]

        project_id = req.query.get("projectId")
        if not project_id:
            project_id = await ObjectAPIHandler._get_project_id(user_id, project_service)

        unsafe = req.query.get("unsafe", "").lower() == "true"

        workflow = SubmissionWorkflow(workflow_name)
        if workflow not in SUBMISSION_CONFIG.delete_submission_workflows:
            raise UserException(f"Unsupported workflow: {workflow.value}")

        try:
            # Check that submission is modifiable.
            submission_id = await SubmissionAPIHandler.check_submission_modifiable(
                req, submission_id, workflow=workflow, project_id=project_id, search_name=True, unsafe=unsafe
            )
            # Delete submission.
            await submission_service.delete_submission(submission_id)
            return web.Response(status=204)

        except UnknownSubmissionUserException:
            return web.Response(status=204)

    @staticmethod
    async def is_submission(req: Request) -> Response:
        """
        Check if the submission exists given submission id or name.

        :param req: HTTP request
        """
        project_service = get_project_service(req)
        user_id = get_authorized_user_id(req)

        workflow_name = req.match_info["workflow"]
        submission_id = req.match_info["submissionId"]

        project_id = req.query.get("projectId")
        if not project_id:
            project_id = await ObjectAPIHandler._get_project_id(user_id, project_service)

        # Verify workflow.
        workflow = SubmissionWorkflow(workflow_name)
        if workflow not in SUBMISSION_CONFIG.is_submission_workflows:
            raise UserException(f"Unsupported workflow: {workflow.value}")

        try:
            # Check that submission is retrievable.
            await SubmissionAPIHandler.check_submission_retrievable(
                req, submission_id, workflow=workflow, project_id=project_id, search_name=True
            )
            return web.Response(status=204)
        except UnknownSubmissionUserException:
            return web.Response(status=404)

    @staticmethod
    async def update_submission(req: Request) -> Response:
        """
        Update a submission given workflow specific documents and return the submission document.

        :param req: POST multipart/form-data request
        :returns: The submission document.
        """
        project_service = get_project_service(req)

        user_id = get_authorized_user_id(req)
        workflow_name = req.match_info["workflow"]
        submission_id = req.match_info["submissionId"]

        project_id = req.query.get("projectId")
        if not project_id:
            project_id = await ObjectAPIHandler._get_project_id(user_id, project_service)

        unsafe = req.query.get("unsafe", "").lower() == "true"

        workflow = SubmissionWorkflow(workflow_name)
        if workflow not in SUBMISSION_CONFIG.update_submission_workflows:
            raise UserException(f"Unsupported workflow: {workflow.value}")

        try:
            # Check that submission is modifiable.
            submission_id = await SubmissionAPIHandler.check_submission_modifiable(
                req, submission_id, workflow=workflow, project_id=project_id, search_name=True, unsafe=unsafe
            )
        except UnknownSubmissionUserException:
            return web.Response(status=404)

        # Update submission.
        objects = await ObjectAPIHandler._get_object_submission_files(req, workflow)
        object_submission_service = await ObjectAPIHandler._get_object_submission_service(req, workflow)
        submission = await object_submission_service.update(user_id, project_id, submission_id, objects)

        return web.json_response(to_json_dict(submission))

    async def list_objects(self, req: Request) -> Response:
        """
        List metadata objects in a submission given optional object type or schema type.

        :param req: GET request
        :returns: Metadata objects in a submission.
        """
        submission_service = get_submission_service(req)
        object_service = get_object_service(req)

        submission_id = req.match_info["submissionId"]
        project_id = req.query.get("projectId")  # Optional project id. Required to search submission name.
        object_type = req.query.get("objectType")
        schema_type = req.query.get("schemaType")

        # Check that the submission is retrievable.
        try:
            submission_id = await SubmissionAPIHandler.check_submission_retrievable(
                req, submission_id, project_id=project_id, search_name=True
            )
        except UnknownSubmissionUserException:
            return web.Response(status=404)

        # Get workflow and project id from the submission.
        workflow = await submission_service.get_workflow(submission_id)

        # Verify workflow.
        if workflow not in SUBMISSION_CONFIG.list_objects_workflows:
            raise UserException(f"Unsupported workflow: {workflow.value}")

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

        return web.json_response(data=to_json_dict(Objects(objects=objects)))

    async def get_objects(self, req: Request) -> web.StreamResponse:
        """
        Get metadata documents in a submission given mandatory object type or schema type.

        :param req: GET request
        :returns: Metadata documents in a submission.
        """
        submission_service = get_submission_service(req)
        object_service = get_object_service(req)

        submission_id = req.match_info["submissionId"]
        project_id = req.query.get("projectId")  # Optional project id. Required to search submission name.
        object_type = req.query.get("objectType")
        schema_type = req.query.get("schemaType")
        object_id = req.query.get("objectId")
        object_name = req.query.get("objectName")

        # Check that the submission can be retrieved by the user.
        submission_id = await SubmissionAPIHandler.check_submission_retrievable(
            req, submission_id, project_id=project_id, search_name=True
        )
        # Get workflow and project id from the submission.
        workflow = await submission_service.get_workflow(submission_id)

        # Verify workflow.
        if workflow not in SUBMISSION_CONFIG.get_objects_workflows:
            raise UserException(f"Unsupported workflow: {workflow.value}")

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

        # Start streaming response.
        resp = web.StreamResponse(status=200, reason="OK", headers={"Content-Type": "application/xml"})
        await resp.prepare(req)

        await XmlDocumentProcessor.write_xml_document(
            xml_config, xmls(), resp.write, object_type=object_type, schema_type=schema_type
        )

        # End of streaming response.
        await resp.write_eof()
        return resp

    @staticmethod
    async def _get_object_submission_files(req: Request, workflow: SubmissionWorkflow) -> list[ObjectSubmission]:
        """
        Get object submission files from multipart/form-data or from the request body.

        :param req: HTTP request
        :param workflow: The submission workflow.
        :return: The object submission files.
        """

        if req.content_type == "multipart/form-data":
            reader = await req.multipart()
            objects = []
            async for part in reader:
                part = cast(BodyPartReader, part)
                if part.filename:
                    objects.append(
                        ObjectSubmission(filename=part.filename, document=(await part.read()).decode("utf-8"))
                    )
            return objects

        if workflow == SubmissionWorkflow.SD:
            return [ObjectSubmission(filename="submission.json", document=await req.text())]

        raise web.HTTPBadRequest()

    @staticmethod
    async def _get_object_submission_service(req: Request, workflow: SubmissionWorkflow) -> ObjectSubmissionService:
        """
        Get object submission service.

        :param req: HTTP request
        :param workflow: The submission workflow.
        :return: The object submission service.
        """
        project_service = get_project_service(req)
        submission_service = get_submission_service(req)
        object_service = get_object_service(req)
        file_service = get_file_service(req)
        session_factory = get_session_factory(req)

        if workflow == SubmissionWorkflow.SD:
            return SensitiveDataObjectSubmissionService(
                project_service, submission_service, object_service, file_service, session_factory
            )
        elif workflow == SubmissionWorkflow.BP:
            return BigPictureObjectSubmissionService(
                project_service, submission_service, object_service, file_service, session_factory
            )
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
