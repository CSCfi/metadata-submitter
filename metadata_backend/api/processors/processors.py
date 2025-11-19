"""Metadata object processor to inject accession numbers."""

from abc import ABC, abstractmethod
from typing import Sequence

from .models import ObjectIdentifier


class ObjectProcessor(ABC):
    """
    Process one metadata object to inject accession numbers.
    """

    @abstractmethod
    def get_object_title(self) -> str | None:
        """
        Retrieve the metadata object title.

        :return: metadata object title.
        """

    @abstractmethod
    def get_object_description(self) -> str | None:
        """
        Retrieve the metadata object description.

        :return: metadata object description.
        """


class DocumentsProcessor(ABC):
    """Process one or more documents objects to inject accession numbers."""

    @abstractmethod
    def get_object_processor(self, schema_type: str, root_path: str, name: str) -> ObjectProcessor:
        """
        Retrieve the metadata object processor.

        :param schema_type: The schema type.
        :param root_path: The metadata object root path.
        :param name: The unique metadata object name.
        :return: metadata object processor.
        """

    @abstractmethod
    def get_object_identifiers(self, schema_type: str | None = None) -> Sequence[ObjectIdentifier]:
        """
        Retrieve the metadata object identifiers.

        :param schema_type: The schema type.
        :return: metadata object identifiers.
        """

    @abstractmethod
    def get_object_references(self) -> Sequence[ObjectIdentifier]:
        """
        Retrieve the metadata object references.

        :return: The metadata object references.
        """

    @abstractmethod
    def set_object_id(self, identifier: ObjectIdentifier) -> None:
        """
        Set the metadata object id.

        :param identifier: The metadata object identifier.
        """

    @abstractmethod
    def get_references_without_ids(self) -> Sequence[ObjectIdentifier]:
        """
        Return metadata object references without ids.

        :return: metadata object references without ids.
        """
