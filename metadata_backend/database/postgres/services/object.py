"""Service for metadata objects."""

import copy
from typing import Any, AsyncIterator

from ....api.exceptions import NotFoundUserException
from ....api.models import Object
from ..models import ObjectEntity
from ..repositories.object import ObjectRepository
from ..repository import transaction


class UnknownObjectException(NotFoundUserException):
    """Raised when a metadata object cannot be found."""

    def __init__(self, object_id: str) -> None:
        """
        Initialize the exception.

        :param object_id: The object id or name.
        """

        message = f"Metadata object '{object_id}' not found."
        super().__init__(message)


class ObjectService:
    """Service for metadata objects."""

    def __init__(self, repository: ObjectRepository) -> None:
        """Initialize the service."""
        self.repository = repository

    @staticmethod
    def convert_from_entity(entity: ObjectEntity) -> dict[str, Any] | None:
        """
        Convert metadata object JSON document to a metadata object dict.

        :param entity: the metadata object entity
        :returns: the metadata object dict
        """

        if entity is None:
            return None

        # Make a deepcopy to prevent SQLAlchemy from tracking changes to the document.
        document = copy.deepcopy(entity.document)
        document["accessionId"] = entity.object_id
        return document

    async def add_object(
        self,
        submission_id: str,
        schema: str,
        *,
        document: dict[str, Any] | None = None,
        xml_document: str | None = None,
        object_id: str | None = None,
        name: str | None = None,
        title: str | None = None,
        is_draft: bool | None = None,
    ) -> str:
        """Add a new metadata object to the database.

        :param submission_id: the submission id
        :param schema: the metadata object type
        :param document: the object metadata JSON document
        :param xml_document: the object metadata XML document
        :param object_id: metadata object id that overrides the default one
        :param name: the metadata object name
        :param title: metadata object title
        :param is_draft: If True, return draft documents.
                         If False, return finalized documents.
                         If None, return all documents.
        :returns: the metadata object id
        """

        obj = ObjectEntity(
            submission_id=submission_id,
            schema=schema,
            document=document,
            xml_document=xml_document,
            object_id=object_id,
            name=name,
            title=title,
        )

        if object_id is not None:
            obj.object_id = object_id
        if is_draft is not None:
            obj.is_draft = is_draft

        return await self.repository.add_object(obj)

    async def is_object(self, object_id: str, *, submission_id: str | None = None) -> bool:
        """Check if the metadata object exists.

        Optionally checks if the metadata object is associated with the given submission id.

        :param object_id: the object id
        :param submission_id: the submission id
        :returns: True if the metadata object exists. If the submission id is given then returns True
                  only if the metadata object is associated with the submission.
        """
        obj = await self.repository.get_object_by_id(object_id)
        if obj is None:
            return False

        if submission_id is not None:
            return obj.submission_id == submission_id

        return True

    async def check_object(self, object_id: str, *, submission_id: str | None = None) -> None:
        """Check if the metadata object exists. Raises an exception if it does not.

        Optionally checks if the metadata object is associated with the given submission id.

        :param object_id: the object id
        :param submission_id: the submission id
        :returns: True if the metadata object exists. If the submission id is given then returns True
                  only if the metadata object is associated with the submission.
        """
        obj = await self.repository.get_object_by_id(object_id)
        if obj is None:
            raise UnknownObjectException(object_id)

        if submission_id is not None:
            if obj.submission_id != submission_id:
                raise UnknownObjectException(object_id)

    async def count_objects(
        self, submission_id: str, schema: str | None = None, *, is_draft: bool | None = None
    ) -> int:
        """
        Count metadata object entities associated with the given submission.

        Args:
            submission_id: the submission id.
            schema: filter by object type.
            is_draft: filter by is draft.

        Returns:
            The number of matching metadata object entities.
        """

        return await self.repository.count_objects(submission_id, schema, is_draft=is_draft)

    async def get_objects(self, submission_id: str, schema: str, *, is_draft: bool | None = None) -> list[Object]:
        """
        Retrieve metadata objects associated with the given submission.

        :param submission_id: The submission id.
        :param schema: The metadata object type.
        :param is_draft: If True, return draft documents.
                         If False, return finalized documents.
                         If None, return all documents.
        :return: The metadata objects.
        """
        objects = []
        async for obj in self.repository.get_objects(submission_id, schema, is_draft=is_draft):
            objects.append(Object(object_id=obj.object_id, submission_id=obj.submission_id, schema_type=obj.schema))
        return objects

    async def get_document(self, object_id: str) -> dict[str, Any]:
        """
        Retrieve metadata object JSON document with the given object id.

        :param object_id: The object id.
        :return: The metadata object document.
        """
        obj = await self.repository.get_object_by_id(object_id)
        if obj is None:
            raise UnknownObjectException(object_id)

        return self.convert_from_entity(obj)

    async def get_documents(
        self, submission_id: str, schema: str, *, is_draft: bool | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Retrieve metadata object JSON documents associated with the given submission.

        :param submission_id: The submission id.
        :param schema: The metadata object type.
        :param is_draft: If True, return draft documents.
                         If False, return finalized documents.
                         If None, return all documents.
        :return: An asynchronous iterator of dictionaries representing the metadata object JSON documents.
        """
        async with transaction(self.repository._session_factory):
            async for obj in self.repository.get_objects(submission_id, schema, is_draft=is_draft):
                yield self.convert_from_entity(obj)

    async def get_xml_document(self, object_id: str) -> str:
        """
        Retrieve metadata object XML document with the given object id.

        :param object_id: The object id.
        :return: The metadata object document.
        """
        obj = await self.repository.get_object_by_id(object_id)
        if obj is None:
            raise UnknownObjectException(object_id)

        return obj.xml_document

    async def get_xml_documents(
        self, submission_id: str, schema: str, *, is_draft: bool | None = None
    ) -> AsyncIterator[str]:
        """
        Retrieve metadata object XML documents associated with the given submission.

        :param submission_id: The submission id.
        :param schema: The metadata object type.
        :param is_draft: If True, return draft documents.
                         If False, return finalized documents.
                         If None, return all documents.
        :return: An asynchronous iterator of dictionaries representing the metadata object XML documents.
        """
        async for obj in self.repository.get_objects(submission_id, schema, is_draft=is_draft):
            yield obj.xml_document

    async def get_submission_id(self, object_id: str) -> str:
        """
        Get the submission id for the metadata object.

        Args:
            object_id: The object id.

        Returns:
            The submission id for the metadata object.
        """
        obj = await self.repository.get_object_by_id(object_id)
        if obj is None:
            raise UnknownObjectException(object_id)

        return obj.submission_id

    async def get_schema(self, object_id: str) -> str:
        """
        Get the object type the metadata object.

        Args:
            object_id: The object id.

        Returns:
            The submission id for the metadata object.
        """
        obj = await self.repository.get_object_by_id(object_id)
        if obj is None:
            raise UnknownObjectException(object_id)

        return obj.schema

    async def update_document(self, object_id: str, document: dict[str, Any]) -> None:
        """Update metadata object JSON document.

        :param object_id: the object id
        :param document: new metadata object document.
        """

        def update_callback(obj: ObjectEntity) -> None:
            obj.document = document

        if await self.repository.update_object(object_id, update_callback) is None:
            raise UnknownObjectException(object_id)

    async def update_xml_document(self, object_id: str, xml_document: str) -> None:
        """Update metadata object XML document.

        :param object_id: the object id
        :param xml_document: new metadata object document.
        """

        def update_callback(obj: ObjectEntity) -> None:
            obj.xml_document = xml_document

        if await self.repository.update_object(object_id, update_callback) is None:
            raise UnknownObjectException(object_id)

    async def delete_object_by_id(self, object_id: str) -> None:
        """Delete metadata object.

        :param object_id: the metadata submission id
        """
        if not await self.repository.delete_object_by_id(object_id):
            raise UnknownObjectException(object_id)

    async def delete_drafts(self, submission_id: str) -> None:
        """Delete draft metadata objects.

        :param submission_id: the submission id
        """
        await self.repository.delete_drafts(submission_id)
