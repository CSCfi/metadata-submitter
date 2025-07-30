"""Handle HTTP methods for server."""

import json

from aiohttp import web
from aiohttp.web import Request, Response

from ...conf.conf import API_PREFIX, get_workflow
from ...helpers.logger import LOG
from ..exceptions import UserException
from ..resources import get_json_object_service, get_object_service, get_submission_service, get_xml_object_service
from .common import to_json
from .restapi import RESTAPIIntegrationHandler
from .submission import SubmissionAPIHandler


class ObjectAPIHandler(RESTAPIIntegrationHandler):
    """API Handler for Objects."""

    @staticmethod
    async def _process_save_metadata_object_request(req: Request) -> tuple[str, str]:
        """
        Process a metadata object save request.

        :param req: HTTP request
        :returns: A tuple of the content type and the request body.
        """

        data = await req.text()

        if req.content_type in {"application/xml", "text/xml"}:
            return "application/xml", data

        if req.content_type in {"application/json", "text/json"}:
            return "application/json", data

        if req.query.get("format", "").lower() == "xml":
            return "application/xml", data

        if data.startswith("<"):
            return "application/xml", data

        return "application/json", data

    @staticmethod
    def _process_get_metadata_object_request(req: Request) -> str:
        """
        Process a metadata object get request.

        :param req: HTTP request
        :returns: the content type.
        """

        if req.content_type in {"application/xml", "text/xml"}:
            return "application/xml"

        if req.content_type in {"application/json", "text/json"}:
            return "application/json"

        if req.query.get("format", "").lower() == "xml":
            return "application/xml"

        return "application/json"

    @staticmethod
    async def check_schema(req: Request, submission_id: str, schema_type: str) -> None:
        """
        Check that object schema is supported for the submission.

        :param req: HTTP request
        :param submission_id: The submission id
        :param schema_type: The metadata object schema type
        """
        submission_service = get_submission_service(req)

        # Check that the workflow supports the schema.
        workflow_name = (await submission_service.get_workflow(submission_id)).value
        workflow = get_workflow(workflow_name)
        if schema_type not in workflow.schemas:
            raise UserException(
                f"Submission '{submission_id}' of type '{workflow.name}' does not support '{schema_type}' objects."
            )

    @staticmethod
    async def get_objects(req: Request) -> Response:
        """Get metadata object ids.

        :param req: GET request
        :returns: The metadata ids.
        """
        submission_id = req.query.get("submission", "")
        if not submission_id:
            raise web.HTTPBadRequest(reason="Missing required query parameter: submission")
        schema = req.match_info["schema"]
        object_service = get_object_service(req)

        # Check that the submission can be retrieved by the user.
        await SubmissionAPIHandler.check_submission_retrievable(req, submission_id)

        LOG.info("GET objects with submission ID: %r.", submission_id)

        data = [obj.json_dump() for obj in await object_service.get_objects(submission_id, schema)]
        return web.json_response(data=data, status=200)

    @staticmethod
    async def get_object(req: Request) -> Response:
        """Get JSON or XML metadata document from the database.

        :param req: GET request
        :returns: The JSON or XML metadata document
        """
        accession_id = req.match_info["accessionId"]

        object_service = get_object_service(req)

        # Check that the submission can be retrieved by the user.
        submission_id = await object_service.get_submission_id(accession_id)
        await SubmissionAPIHandler.check_submission_retrievable(req, submission_id)

        content_type = ObjectAPIHandler._process_get_metadata_object_request(req)

        if content_type == "application/xml":
            body = await object_service.get_xml_document(accession_id)
        else:
            body = to_json(await object_service.get_document(accession_id))

        LOG.info("GET object with accession ID: %r.", accession_id)
        return web.Response(body=body, status=200, content_type=content_type)

    @staticmethod
    async def post_object(req: Request) -> Response:
        """Save metadata object to database.

        For JSON request body we validate it is consistent with the associated JSON schema.
        For CSV upload we allow it for a select number objects, currently: ``sample``.

        :param req: POST request
        :returns: JSON response containing accessionId for submitted object
        """
        schema_type = req.match_info["schema"]
        submission_id = req.query.get("submission", "")
        if not submission_id:
            raise web.HTTPBadRequest(reason="Missing required query parameter: submission")
        validate = not req.path.startswith(f"{API_PREFIX}/drafts")

        json_object_service = get_json_object_service(req)
        xml_object_service = get_xml_object_service(req)

        # Check that the submission can be modified by the user.
        await SubmissionAPIHandler.check_submission_modifiable(req, submission_id)

        # Check that the schema is supported by the workflow.
        await ObjectAPIHandler.check_schema(req, submission_id, schema_type)

        content_type, data = await ObjectAPIHandler._process_save_metadata_object_request(req)

        if content_type == "application/xml":
            documents = await xml_object_service.add_metadata_objects(submission_id, schema_type, data, validate)
        else:
            try:
                json_data = json.loads(data)
            except Exception as ex:
                raise web.HTTPBadRequest(reason=f"Invalid JSON payload: str{ex}")

            documents = await json_object_service.add_metadata_objects(submission_id, schema_type, json_data, validate)

        return web.Response(
            body=to_json(documents),
            status=201,
            content_type="application/json",
        )

    @staticmethod
    async def delete_object(req: Request) -> web.HTTPNoContent:
        """Delete metadata object from database.

        :param req: DELETE request
        :raises: HTTPUnauthorized if submission published
        :raises: HTTPUnprocessableEntity if object does not belong to current user
        :returns: HTTPNoContent response
        """
        schema_type = req.match_info["schema"]
        accession_id = req.match_info["accessionId"]
        LOG.debug("Deleting object in collection: %r with accession ID: %r.", schema_type, accession_id)

        object_service = get_object_service(req)

        # Check that the submission can be modified by the user.
        submission_id = await object_service.get_submission_id(accession_id)
        await SubmissionAPIHandler.check_submission_modifiable(req, submission_id)

        if schema_type != await object_service.get_schema(accession_id):
            raise UserException("Invalid object schema.")

        await object_service.delete_object_by_id(accession_id)

        LOG.info(
            "DELETE object with accession ID: %s, schema: %s was successful.",
            accession_id,
            schema_type,
        )
        return web.HTTPNoContent()

    @staticmethod
    async def put_or_patch_object(req: Request) -> Response:
        """Add or replace metadata object in database.

        :param req: PUT request
        :raises: HTTPUnsupportedMediaType if JSON replace is attempted
        :returns: JSON response containing accessionId for submitted object
        """
        schema_type = req.match_info["schema"]
        accession_id = req.match_info["accessionId"]
        validate = not req.path.startswith(f"{API_PREFIX}/drafts")

        object_service = get_object_service(req)
        json_object_service = get_json_object_service(req)
        xml_object_service = get_xml_object_service(req)

        # Check that the submission can be modified by the user.
        submission_id = await object_service.get_submission_id(accession_id)
        await SubmissionAPIHandler.check_submission_modifiable(req, submission_id)

        # Check that the schema is supported by the workflow.
        await ObjectAPIHandler.check_schema(req, submission_id, schema_type)

        content_type, data = await ObjectAPIHandler._process_save_metadata_object_request(req)

        if content_type == "application/xml":
            await xml_object_service.update_metadata_object(submission_id, accession_id, schema_type, data, validate)
        else:
            try:
                json_data = json.loads(data)
            except Exception as ex:
                raise web.HTTPBadRequest(reason=f"Invalid JSON payload: str{ex}")

            await json_object_service.update_metadata_object(
                submission_id, accession_id, schema_type, json_data, validate
            )

        LOG.info("PUT object with accession ID: %r with schema type %r was successful.", accession_id, schema_type)
        return web.Response(body=to_json({"accessionId": accession_id}), status=200, content_type="application/json")
