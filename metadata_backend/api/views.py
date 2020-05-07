import json
import xmltodict

from aiohttp import web

from ..database.db_services import CRUDService, MongoDBService
from ..helpers.schema_load import SchemaLoader
from ..helpers.validator import XMLValidator
from ..helpers.logger import LOG, get_attributes


class SiteHandler:
    """ Backend feature handling, speaks to db via db_service objects"""

    def __init__(self):
        """ Create needed services for connecting to database. """
        self.schema_db_service = MongoDBService("schemas")
        self.submission_db_service = MongoDBService("submissions")
        self.backup_db_service = MongoDBService("backups")

    async def submit(self, request):
        """Handles submission to server
        :param request: POST request sent
        :raises: HTTP Exceptions with status code 201 or 400
        :returns: JSON response with submitted xml_content or validation error
        reason
        """

        reader = await request.multipart()
        field = await reader.next()
        schema = field.name
        result = []
        while True:
            chunk = await field.read_chunk()
            if not chunk:
                break
            result.append(chunk)
        xml_content = ''.join(x.decode('UTF-8') for x in result)
        schema_loader = SchemaLoader()
        try:
            valid_xml = XMLValidator.validate(xml_content, schema,
                                              schema_loader)
        except ValueError as error:
            reason = f"{error} {schema}"
            raise web.HTTPBadRequest(reason=reason)

        if not valid_xml:
            reason = f"Submitted XML file was not valid against schema {schema}"
            raise web.HTTPBadRequest(reason=reason)

        # TODO: Parse metadata XML to valid JSON object here, follow JSON
        # schema. At the moment XML is just dumped to db as one chunk

        xml_content_json = {"content": xml_content}
        CRUDService.create(self.submission_db_service, schema, xml_content_json)

        # TODO: Create xml backup to different database here

        # TODO: Create correct response here (e.g. get REST api address
        # to document that was inserted to db and return it with inserted
        # json data
        raise web.HTTPCreated(body=xml_content, content_type="text/xml")
