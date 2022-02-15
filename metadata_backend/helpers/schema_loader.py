"""Utility class to find XSD Schema that can be used to test XML files.

Current implementation relies on searching XSD files from folder, should
probably be replaced with database searching in the future.
"""

import ujson
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from xmlschema import XMLSchema

SCHEMAS_ROOT = Path(__file__).parent / "schemas"


class SchemaNotFoundException(Exception):
    """Custom exception to be raised when schema is not found."""

    def __init__(self) -> None:
        """Set up exception message."""
        Exception.__init__(self, "The provided schema type could not be found.")


class SchemaLoader(ABC):
    """XML Schema Loader implementation."""

    def __init__(self, loader_type: str) -> None:
        """Load schemas folder on initialization and set loader."""
        self.path = SCHEMAS_ROOT
        self.loader_type = loader_type.lower()

    def _identify_file(self, schema_type: str) -> Path:
        """Identify file in schemas folder.

        :param schema_type: Schema type to be searched for
        :returns: file
        :raises SchemaNotFoundException: If searched schema doesn't exist
        """
        schema_type = schema_type.lower()
        schema_file = None
        for file in set([x for x in self.path.iterdir()]):
            if schema_type in file.name and file.name.endswith(self.loader_type):
                schema_file = file
                break
        if not schema_file:
            raise SchemaNotFoundException

        return schema_file

    @abstractmethod
    def get_schema(self, schema_type: str) -> Any:
        """Find schema which is used to match files against.

        Must be implemented by subclass.
        """


class XMLSchemaLoader(SchemaLoader):
    """XML Schema Loader implementation."""

    def __init__(self) -> None:
        """Select loader type on initialization."""
        super().__init__("xsd")

    def get_schema(self, schema_type: str) -> XMLSchema:
        """Find schema which is used to match XML files against.

        Documentation of XMLSchema project:
        https://xmlschema.readthedocs.io/en/latest/

        We look for files ending in xsd to avoid any mismatch on
        what schema is loaded.

        :param schema_type: Schema type to be searched for
        :returns: XMLSchema able to validate XML against defined schema type
        :raises SchemaNotFoundException: If searched schema doesn't exist
        """
        file = self._identify_file(schema_type)
        with file.open() as f:
            schema_content = f.read()
        return XMLSchema(schema_content, base_url=self.path.as_posix())


class JSONSchemaLoader(SchemaLoader):
    """JSON Loader implementation."""

    def __init__(self) -> None:
        """Select loader type on initialization."""
        super().__init__("json")

    def get_schema(self, schema_type: str) -> dict:
        """Find schema which is used to match JSON files against.

        :param schema_type: Schema type to be searched for
        :returns: JSONSchema able to validate XML against defined schema type
        :raises SchemaNotFoundException: If searched schema doesn't exist
        """
        file = self._identify_file(schema_type)
        with file.open() as f:
            schema_content = ujson.load(f)
        return schema_content
