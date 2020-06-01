"""Utility class to find XSD Schema that can be used to test XML files.

Current implementation relies on searching XSD files from folder, should
probably be replaced with database searching in the future.
"""

from pathlib import Path

from xmlschema import XMLSchema

SCHEMAS_ROOT = Path(__file__).parent / 'schemas'


class SchemaNotFoundException(Exception):
    """Custom exception to be raised when schema is not found."""

    def __init__(self) -> None:
        """Set up exception message."""
        Exception.__init__(self, "There is no xsd file for given schema.")


class SchemaLoader:
    """Loader implementation."""

    def __init__(self) -> None:
        """Load schemas folder on initialization."""
        self.path = SCHEMAS_ROOT

    def get_schema(self, schema_name: str) -> XMLSchema:
        """Find schema which is used to match XML files against.

        Documentation of XMLSchema project:
        https://xmlschema.readthedocs.io/en/latest/

        :param schema_name: Schema to be searched for
        :returns: XMLSchema able to validate XML against defined schema
        :raises SchemaNotFoundException: If searched schema doesn't exist
        """
        schema_name = schema_name.lower()
        schema_file = None
        for file in [x for x in self.path.iterdir()]:
            if schema_name in file.name:
                with file.open() as f:
                    schema_file = f.read()
        if not schema_file:
            raise SchemaNotFoundException
        schema = XMLSchema(schema_file, base_url=self.path.as_posix())
        return schema
