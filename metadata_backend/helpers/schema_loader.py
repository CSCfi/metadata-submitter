"""Utility class to find XSD Schema that can be used to test XML files.

Current implementation relies on searching XSD files from folder, should
probably be replaced with database searching in the future.
"""

from pathlib import Path

from xmlschema import XMLSchema
import json

SCHEMAS_ROOT = Path(__file__).parent / 'schemas'


class SchemaNotFoundException(Exception):
    """Custom exception to be raised when schema is not found."""

    def __init__(self) -> None:
        """Set up exception message."""
        Exception.__init__(self, "There is no file for given schema.")


class XMLSchemaLoader:
    """XML Schema Loader implementation."""

    def __init__(self) -> None:
        """Load schemas folder on initialization."""
        self.path = SCHEMAS_ROOT

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
        schema_type = schema_type.lower()
        schema_file = None
        for file in [x for x in self.path.iterdir()]:
            if schema_type in file.name and file.name.endswith("xsd"):
                with file.open() as f:
                    schema_file = f.read()
        if not schema_file:
            raise SchemaNotFoundException
        return XMLSchema(schema_file, base_url=self.path.as_posix())


class JSONSchemaLoader:
    """JSON Loader implementation."""

    def __init__(self) -> None:
        """Load schemas folder on initialization."""
        self.path = SCHEMAS_ROOT

    def get_schema(self, schema_type: str) -> dict:
        """Find schema which is used to match JSON files against.

        :param schema_type: Schema type to be searched for
        :returns: JSONSchema able to validate XML against defined schema type
        :raises SchemaNotFoundException: If searched schema doesn't exist
        """
        schema_type = schema_type.lower()
        schema_file = None
        for file in [x for x in self.path.iterdir()]:
            if schema_type in file.name and file.name.endswith("json"):
                with file.open() as f:
                    schema_file = json.load(f)
        if not schema_file:
            raise SchemaNotFoundException
        return schema_file
