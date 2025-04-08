"""XML object operator class."""

from typing import Any

from aiohttp import web
from motor.motor_asyncio import AsyncIOMotorClient

from ...helpers.logger import LOG
from ...helpers.parser import XMLToJSONParser
from .object import ObjectOperator
from .object_base import BaseObjectOperator


class XMLObjectOperator(BaseObjectOperator):
    """Alternative operator class for handling metadata object related database operations.

    We store the XML data in a database ``XML-{schema}``.
    Operations are implemented with XML format.
    """

    def __init__(self, db_client: AsyncIOMotorClient) -> None:  # type: ignore
        """Initialize database and content-type.

        :param db_client: Motor client used for database connections. Should be
        running on same loop with aiohttp, so needs to be passed from aiohttp
        Application.
        """
        super().__init__("text/xml", db_client)

    async def _format_data_to_create_and_add_to_db(self, schema_type: str, data: str) -> list[dict[str, Any]]:
        """Format XML metadata object and add it to db.

        XML is validated, then parsed to JSON, which is added to database.
        After successful JSON insertion, XML itself is backed up to database.

        :param schema_type: Schema type of the object to read.
        :param data: Original XML content
        :returns: List of metadata objects extracted from the XML content
        """
        db_client = self.db_service.db_client
        parser = XMLToJSONParser()
        # remove `draft-` from schema type
        schema = schema_type[6:] if schema_type.startswith("draft") else schema_type
        parsed_json_data, parsed_xml_content = parser.parse(schema, data)

        # Parser may return a list of objects and each object should be added separately
        data_objects = parsed_json_data if isinstance(parsed_json_data, list) else [parsed_json_data]
        added_data: list[dict[str, Any]] = []
        for i, obj in enumerate(data_objects):
            data_with_id = await ObjectOperator(db_client)._format_data_to_create_and_add_to_db(schema_type, obj)
            added_data.append(data_with_id)
            xml_obj: str = parsed_xml_content[i]
            # Alter the xml content for Bigpicture XML items
            if schema[:2] == "bp":
                xml_obj = parser.assign_accession_to_xml_content(
                    schema, parsed_xml_content[i], data_with_id["accessionId"]
                )
            LOG.debug("XMLObjectOperator formatted data for collection: 'xml-%s' to add to DB.", schema_type)
            await self._insert_formatted_object_to_db(
                f"xml-{schema_type}", {"accessionId": data_with_id["accessionId"], "content": xml_obj}
            )

        return added_data

    async def _format_data_to_replace_and_add_to_db(
        self, schema_type: str, accession_id: str, data: str
    ) -> dict[str, Any]:
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
        data_as_json, parsed_xml = XMLToJSONParser().parse(schema, data)
        data_with_id = await ObjectOperator(db_client)._format_data_to_replace_and_add_to_db(
            schema_type, accession_id, data_as_json
        )
        LOG.debug("XMLObjectOperator formatted data for collection: 'xml-%s' to add to DB.", schema_type)
        await self._replace_object_from_db(
            f"xml-{schema_type}", accession_id, {"accessionId": accession_id, "content": parsed_xml[0]}
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

    async def _format_read_data(self, schema_type: str, data_raw: dict[str, Any]) -> str:
        """Get XML content from given mongodb data.

        :param schema_type: Schema type of the object to read.
        :param data_raw: Data from mongodb query with single result.
        :returns: XML content
        """
        data: str = data_raw["content"]
        return data
