"""HTTP handler for object related requests."""

from typing import AsyncIterator, Sequence, cast

from aiohttp import BodyPartReader, web
from aiohttp.web import Request, Response

from ...conf.conf import get_workflow
from ..auth import get_authorized_user_id
from ..exceptions import UserException
from ..models import Objects, SubmissionWorkflow
from ..processors.xml.configs import BP_FULL_SUBMISSION_XML_OBJECT_CONFIG
from ..processors.xml.models import XmlObjectConfig
from ..processors.xml.processors import XmlDocumentProcessor
from ..resources import (
    get_object_service,
    get_project_service,
    get_session_factory,
    get_submission_service,
)
from ..services.submission import ObjectSubmissionService
from .restapi import RESTAPIIntegrationHandler
from .submission import SubmissionAPIHandler


class ObjectAPIHandler(RESTAPIIntegrationHandler):
    """API Handler for Objects."""

    @staticmethod
    async def post_submission(req: Request) -> Response:
        """
        Create a submission given workflow specific documents and return the submission document.

        :param req: POST multipart/form-data request
        :returns: The submission document.
        """
        project_service = get_project_service(req)
        submission_service = get_submission_service(req)
        object_service = get_object_service(req)
        session_factory = get_session_factory(req)

        user_id = get_authorized_user_id(req)
        workflow_name = req.match_info["workflow"]
        project_id = req.match_info["projectId"]

        # Verify workflow.
        workflow = SubmissionWorkflow(get_workflow(workflow_name).name)
        if workflow != SubmissionWorkflow.BP:
            raise UserException(f"Unsupported workflow: {workflow.value}")

        # Verify project.
        await project_service.verify_user_project(user_id, project_id)

        # Read metadata objects from multipart/form-data.
        reader = await req.multipart()
        objects = []
        async for part in reader:
            part = cast(BodyPartReader, part)
            if part.filename:
                objects.append((await part.read()).decode("utf-8"))

        # Process submission.
        object_submission_service = ObjectSubmissionService(
            project_service, submission_service, object_service, session_factory
        )
        submission = await object_submission_service.submit(user_id, project_id, workflow, objects)

        return web.json_response(submission.to_json_dict())

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

        # Check that the submission can be retrieved by the user.
        submission_id = await SubmissionAPIHandler.check_submission_retrievable(
            req, submission_id, project_id=project_id, search_name=True
        )
        # Get workflow and project id from the submission.
        workflow = await submission_service.get_workflow(submission_id)

        # Verify workflow.
        if workflow != SubmissionWorkflow.BP:
            raise UserException(f"Unsupported workflow: {workflow.value}")
        xml_config = BP_FULL_SUBMISSION_XML_OBJECT_CONFIG

        if (schema_type is not None) and (object_type is not None):
            raise UserException("Specify either objectType or schemaType but not both.")

        # Get object types.
        object_types = self._get_xml_object_types(xml_config, object_type, schema_type)

        # Get objects.
        objects = await object_service.get_objects(submission_id, object_types)

        return web.json_response(data=Objects(objects=objects).to_json_dict())

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
        if workflow != SubmissionWorkflow.BP:
            raise UserException(f"Unsupported workflow: {workflow.value}")
        xml_config = BP_FULL_SUBMISSION_XML_OBJECT_CONFIG

        if not (schema_type is not None) ^ (object_type is not None):
            raise UserException("Either objectType or schemaType must be defined.")

        async def xmls() -> AsyncIterator[str]:
            # Get object types.
            object_types = self._get_xml_object_types(xml_config, object_type, schema_type)

            # Get objects.
            objects = await object_service.get_objects(
                submission_id, object_types, object_id=object_id, name=object_name
            )

            # Get documents.
            for obj in objects:
                xml = await object_service.get_xml_document(obj.object_id)
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
