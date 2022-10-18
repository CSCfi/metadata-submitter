"""XML object operator class."""
from typing import Dict, List

from aiohttp import web
from motor.motor_asyncio import AsyncIOMotorClient

from ...conf.conf import mongo_database
from ...helpers.logger import LOG
from ...helpers.parser import XMLToJSONParser
from .base import BaseOperator
from .object import Operator


class XMLOperator(BaseOperator):
    """Alternative operator class for handling metadata object related database operations.

    We store the XML data in a database ``XML-{schema}``.
    Operations are implemented with XML format.
    """

    def __init__(self, db_client: AsyncIOMotorClient) -> None:
        """Initialize database and content-type.

        :param db_client: Motor client used for database connections. Should be
        running on same loop with aiohttp, so needs to be passed from aiohttp
        Application.
        """
        super().__init__(mongo_database, "text/xml", db_client)

    async def _format_data_to_create_and_add_to_db(self, schema_type: str, data: str) -> List[dict]:
        """Format XML metadata object and add it to db.

        XML is validated, then parsed to JSON, which is added to database.
        After successful JSON insertion, XML itself is backed up to database.

        :param schema_type: Schema type of the object to read.
        :param data: Original XML content
        :returns: List of metadata objects extracted from the XML content
        """
        db_client = self.db_service.db_client
        # remove `draft-` from schema type
        schema = schema_type[6:] if schema_type.startswith("draft") else schema_type
        parsed_data = XMLToJSONParser().parse(schema, data)

        # Parser may return a list of objects and each object should be added separately
        data_objects = parsed_data if isinstance(parsed_data, list) else [parsed_data]
        added_data: List = []
        for obj in data_objects:
            data_with_id = await Operator(db_client)._format_data_to_create_and_add_to_db(schema_type, obj)
            added_data.append(data_with_id)
            LOG.debug("XMLOperator formatted data for collection: 'xml-%s' to add to DB.", schema_type)
            await self._insert_formatted_object_to_db(
                f"xml-{schema_type}", {"accessionId": data_with_id["accessionId"], "content": data}
            )

        return added_data

    async def _format_data_to_replace_and_add_to_db(self, schema_type: str, accession_id: str, data: str) -> Dict:
        """Format XML metadata object and add it to db.

        XML is validated, then parsed to JSON, which is added to database.
        After successful JSON insertion, XML itself is backed up to database.

        :param schema_type: Schema type of the object to replace.
        :param accession_id: Identifier of object to replace.
        :param data: Original XML content
        :returns: Metadata object extracted from the XML content
        """
        db_client = self.db_service.db_client
        # remove `draft-` from schema type
        schema = schema_type[6:] if schema_type.startswith("draft") else schema_type
        data_as_json = XMLToJSONParser().parse(schema, data)
        data_with_id = await Operator(db_client)._format_data_to_replace_and_add_to_db(
            schema_type, accession_id, data_as_json
        )
        LOG.debug("XMLOperator formatted data for collection: 'xml-%s' to add to DB.", schema_type)
        await self._replace_object_from_db(
            f"xml-{schema_type}", accession_id, {"accessionId": accession_id, "content": data}
        )
        return data_with_id

    async def _format_data_to_update_and_add_to_db(self, schema_type: str, accession_id: str, data: str) -> str:
        """Raise not implemented.

        Patch update for XML not supported

        :param schema_type: Schema type of the object to replace.
        :param accession_id: Identifier of object to replace.
        :param data: Original XML content
        :raises: HTTPUnsupportedMediaType
        """
        reason = "XML patching is not possible."
        raise web.HTTPUnsupportedMediaType(reason=reason)

    async def _format_read_data(self, schema_type: str, data_raw: Dict) -> str:
        """Get XML content from given mongodb data.

        :param schema_type: Schema type of the object to read.
        :param data_raw: Data from mongodb query with single result.
        :returns: XML content
        """
        return data_raw["content"]
