"""Handle HTTP methods for server."""

import ujson
from aiohttp import web
from aiohttp.web import Request, Response
from xmlschema import XMLSchemaException

from ...helpers.logger import LOG
from ...helpers.schema_loader import SchemaNotFoundException, XMLSchemaLoader
from ...helpers.validator import XMLValidator
from .common import multipart_content
from .object import ObjectAPIHandler


class XMLSubmissionAPIHandler(ObjectAPIHandler):
    """Handler for non-rest API methods."""

    async def validate(self, req: Request) -> Response:
        """Handle validating an XML file sent to endpoint.

        :param req: Multipart POST request with submission.xml and files
        :returns: JSON response indicating if validation was successful or not
        """
        files, _ = await multipart_content(req, extract_one=True, expect_xml=True)
        xml_content, schema_type, _ = files[0]
        validator = await self._perform_validation(schema_type, xml_content)
        return web.Response(
            status=ujson.loads(validator.resp_body)["status"],
            body=validator.resp_body,
            content_type="application/json",
        )

    @staticmethod
    async def _perform_validation(schema_type: str, xml_content: str) -> XMLValidator:
        """Validate an xml.

        :param schema_type: Schema type of the object to validate.
        :param xml_content: Metadata object
        :raises: HTTPBadRequest if schema load fails
        :returns: JSON response indicating if validation was successful or not
        """
        try:
            schema = XMLSchemaLoader().get_schema(schema_type)
            LOG.info("%r XML schema loaded for XML validation.", schema_type)
            return XMLValidator(schema, xml_content)

        except (SchemaNotFoundException, XMLSchemaException) as error:
            reason = f"{error} ({schema_type})"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)
