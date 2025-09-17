"""Loader for schema files."""

from abc import ABC
from pathlib import Path
from typing import Any

import ujson

from metadata_backend.api.exceptions import SystemException

SCHEMA_FILE_ROOT_DIR = Path(__file__).parent / "schemas"


class SchemaFileNotFoundException(SystemException):
    """Exception raised when schema file could not be found."""

    def __init__(self, schema_file: str) -> None:
        """
        Exception raised when schema file could not be found.

        :param schema_file: The schema file.
        """
        super().__init__(f"Could not find schema '{schema_file}'.")


class SchemaLoader(ABC):
    """Loader for schema files."""

    def __init__(self, schema_file_suffix: str) -> None:
        """
        Loader for schema files.

        :param schema_file_suffix: The schema file suffix.
        """

        self.schema_file_suffix = schema_file_suffix

    def get_schema_file(self, schema_file: str) -> Path:
        """Get the schema file given schema file name without suffix.

        :param schema_file: The schema file name without suffix.
        :returns: The schema file path.
        :raises SchemaNotFoundException: If the schema file could not be found.
        """
        for file in SCHEMA_FILE_ROOT_DIR.iterdir():
            if schema_file == file.stem and self.schema_file_suffix.lstrip(".") == file.suffix.lstrip("."):
                return file

        raise SchemaFileNotFoundException(f"{schema_file}.{self.schema_file_suffix}")


class XMLSchemaLoader(SchemaLoader):
    """Loader for XML schema files."""

    def __init__(self) -> None:
        """Loader for XML schema files."""

        super().__init__("xsd")


class JSONSchemaLoader(SchemaLoader):
    """Loader for JSON schema files."""

    def __init__(self) -> None:
        """Loader for JSON schema files."""

        super().__init__("json")

    def get_schema(self, schema_file: str) -> dict[str, Any]:
        """Return JSON schema as a dictionary.

        :param schema_file: The schema file name without suffix.
        :returns: The JSON schema as a dictionary.
        :raises SchemaNotFoundException: If the schema file could not be found.
        """
        file = self.get_schema_file(schema_file)
        with file.open() as f:
            schema_content: dict[str, Any] = ujson.load(f)
        return schema_content
