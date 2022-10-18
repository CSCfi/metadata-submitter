"""Base operator class shared by operators."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple, Union

from aiohttp import web
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, OperationFailure

from ...database.db_service import DBService
from ...helpers.logger import LOG


class BaseOperator(ABC):
    """Base class for operators, implements shared functionality.

    This BaseOperator is mainly addressed for working with objects owned by
    a user and that are clustered by submission.
    :param ABC: The abstract base class
    """

    def __init__(self, db_name: str, content_type: str, db_client: AsyncIOMotorClient) -> None:
        """Init needed variables, must be given by subclass.

        :param db_name: Name for database to save objects to.
        :param content_type: Content type this operator handles (XML or JSON)
        :param db_client: Motor client used for database connections. Should be
        running on same loop with aiohttp, so needs to be passed from aiohttp
        Application.
        """
        self.db_service = DBService(db_name, db_client)
        self.content_type = content_type

    async def create_metadata_object(self, schema_type: str, data: Union[Dict, str]) -> Union[Dict, List[dict]]:
        """Create new metadata object to database.

        Data formatting and addition step for JSON or XML must be implemented
        by corresponding subclass.

        :param schema_type: Schema type (collection) of the object to create.
        :param data: Data to be saved to database.
        :returns: Dict (or list of dicts) with accession id of the object inserted to database and its title
        """
        formatted_data = await self._format_data_to_create_and_add_to_db(schema_type, data)
        data_list: List = formatted_data if isinstance(formatted_data, list) else [formatted_data]
        for obj in data_list:
            _id = obj["accessionId"]
            LOG.info("Inserting object in collection: %r to database succeeded with accession ID: %r", schema_type, _id)
        return formatted_data

    async def replace_metadata_object(self, schema_type: str, accession_id: str, data: Union[Dict, str]) -> Dict:
        """Replace metadata object from database.

        Data formatting and addition step for JSON or XML must be implemented
        by corresponding subclass.

        :param schema_type: Schema type (collection) of the object to replace.
        :param accession_id: Identifier of object to replace.
        :param data: Data to be saved to database.
        :returns: Tuple of Accession id for the object replaced to database and its title
        """
        data = await self._format_data_to_replace_and_add_to_db(schema_type, accession_id, data)
        LOG.info(
            "Replacing object in collection: %r to database succeeded with accession ID: %r",
            schema_type,
            accession_id,
        )
        return data

    async def update_metadata_object(self, schema_type: str, accession_id: str, data: Union[Dict, str]) -> str:
        """Update metadata object from database.

        Data formatting and addition step for JSON or XML must be implemented
        by corresponding subclass.

        :param schema_type: Schema type (collection) of the object to update.
        :param accession_id: Identifier of object to update.
        :param data: Data to be saved to database.
        :returns: Accession id for the object updated to database
        """
        await self._format_data_to_update_and_add_to_db(schema_type, accession_id, data)
        LOG.info(
            "Updated object in collection: %r to database succeeded with accession ID: %r",
            schema_type,
            accession_id,
        )
        return accession_id

    async def read_metadata_object(self, schema_type: str, accession_id: str) -> Tuple[Union[Dict, str], str]:
        """Read metadata object from database.

        Data formatting to JSON or XML must be implemented by corresponding
        subclass.

        :param schema_type: Schema type of the object to read.
        :param accession_id: Accession Id of the object to read.
        :raises: HTTPBadRequest if reading was not successful, HTTPNotFound if no data found
        :returns: Tuple of Metadata object formatted to JSON or XML, content type
        """
        try:
            data_raw = await self.db_service.read(schema_type, accession_id)
            if not data_raw:
                reason = f"Object with '{accession_id}' not found in collection: '{schema_type}'."
                LOG.error(reason)
                raise web.HTTPNotFound(reason=reason)
            data = await self._format_read_data(schema_type, data_raw)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while reading object: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)
        return data, self.content_type

    async def delete_metadata_object(self, schema_type: str, accession_id: str) -> str:
        """Delete metadata object from database.

        Tries to remove both JSON and original XML from database, passes
        silently if objects don't exist in database.

        :param schema_type: Schema type of the object to delete.
        :param accession_id: Accession Id of the object to delete.
        :raises: HTTPBadRequest if deleting was not successful
        :returns: Accession id for the object deleted from the database
        """

        _deletion_success = await self._remove_object_from_db(schema_type, accession_id)
        if _deletion_success:
            LOG.info("%r successfully deleted from collection: %s", accession_id, schema_type)
            return accession_id

        reason = f"Deleting {accession_id} from database failed."
        LOG.error(reason)
        raise web.HTTPBadRequest(reason=reason)

    async def _insert_formatted_object_to_db(self, schema_type: str, data: Dict) -> bool:
        """Insert formatted metadata object to database.

        :param schema_type: Schema type of the object to insert.
        :param data: Single document formatted as JSON
        :returns: Accession Id for object inserted to database
        :raises: HTTPBadRequest if reading was not successful
        :returns: Tuple of Accession id for the object deleted from the database and its title
        """
        try:
            insert_success = await self.db_service.create(schema_type, data)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting object: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)

        if not insert_success:
            reason = "Inserting object to database failed for some reason."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return True

    async def _replace_object_from_db(self, schema_type: str, accession_id: str, data: Dict) -> bool:
        """Replace formatted metadata object in database.

        :param schema_type: Schema type of the object to replace.
        :param accession_id: Identifier of object to replace.
        :param data: Single document formatted as JSON
        :raises: HTTPBadRequest if reading was not successful, HTTPNotFound if no data found
        :returns: Tuple of Accession Id for object inserted to database and its title
        """
        try:
            check_exists = await self.db_service.exists(schema_type, accession_id)
            if not check_exists:
                reason = f"Object with accession ID: '{accession_id}' was not found."
                LOG.error(reason)
                raise web.HTTPNotFound(reason=reason)
            replace_success = await self.db_service.replace(schema_type, accession_id, data)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting object: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)
        if not replace_success:
            reason = "Replacing object to database failed for some reason."
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return True

    async def _update_object_from_db(self, schema_type: str, accession_id: str, data: Dict) -> str:
        """Update formatted metadata object in database.

        After the data has been update we need to do a sanity check
        to see if the patched data still adheres to the corresponding
        JSON schema.

        :param schema_type: Schema type of the object to update.
        :param accession_id: Identifier of object to update.
        :param data: Single document formatted as JSON
        :raises: HTTPBadRequest if reading was not successful, HTTPNotFound if no data found
        :returns: Accession Id for object updated to database
        """
        try:
            check_exists = await self.db_service.exists(schema_type, accession_id)
            if not check_exists:
                reason = f"Object with accession id '{accession_id}' was not found."
                LOG.error(reason)
                raise web.HTTPNotFound(reason=reason)
            update_success = await self.db_service.update(schema_type, accession_id, data)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while getting object: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)
        if update_success:
            return accession_id

        reason = "Replacing object to database failed for some reason."
        LOG.error(reason)
        raise web.HTTPBadRequest(reason=reason)

    async def _remove_object_from_db(self, schema_type: str, accession_id: str) -> bool:
        """Delete object from database.

        We can omit raising error for XMLOperator if id is not
        in backup collection.

        :param schema_type: Schema type of the object to delete.
        :param accession_id: Identifier of object to delete.
        :param data: Single document formatted as JSON
        :raises: HTTPBadRequest if reading was not successful, HTTPNotFound if no data found
        :returns: True or False if object deleted from the database
        """
        try:
            check_exists = await self.db_service.exists(schema_type, accession_id)
            if not check_exists and not schema_type.startswith("xml-"):
                reason = f"Object with accession ID: '{accession_id}' was not found."
                LOG.error(reason)
                raise web.HTTPNotFound(reason=reason)

            delete_success = await self.db_service.delete(schema_type, accession_id)
        except (ConnectionFailure, OperationFailure) as error:
            reason = f"Error happened while deleting object: {error}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason)
        return delete_success

    async def check_exists(self, schema_type: str, accession_id: str) -> None:
        """Check the existance of a object by its id in the database.

        :param schema_type: Schema type of the object to find.
        :param accession_id: Identifier of object to find.
        :raises: HTTPNotFound if object does not exist
        """
        exists = await self.db_service.exists(schema_type, accession_id)
        LOG.debug("Check accession ID: %r exists resulted in: %s", accession_id, exists)
        if not exists:
            reason = f"Object with accession ID: '{accession_id}' from collection: '{schema_type}' was not found."
            LOG.error(reason)
            raise web.HTTPNotFound(reason=reason)

    # no way around type Any here without breaking Liskov substitution principle

    @abstractmethod
    async def _format_data_to_create_and_add_to_db(
        self, schema_type: str, data: Any  # noqa: ANN401
    ) -> Union[Dict, List[dict]]:
        """Format and add data to database.

        Must be implemented by subclass.
        """

    @abstractmethod
    async def _format_data_to_replace_and_add_to_db(
        self, schema_type: str, accession_id: str, data: Any  # noqa: ANN401
    ) -> Dict:
        """Format and replace data in database.

        Must be implemented by subclass.
        """

    @abstractmethod
    async def _format_data_to_update_and_add_to_db(
        self, schema_type: str, accession_id: str, data: Any  # noqa: ANN401
    ) -> str:
        """Format and update data in database.

        Must be implemented by subclass.
        """

    @abstractmethod
    async def _format_read_data(self, schema_type: str, data_raw: Any) -> Any:  # noqa: ANN401
        """Format data for API response.

        Must be implemented by subclass.
        """
