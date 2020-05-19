"""Tests for helper classes."""
import unittest

import xmlschema

from metadata_backend.helpers.schema_load import (SchemaLoader,
                                                  SchemaNotFoundException)


class TestSchemaLoader(unittest.TestCase):
    """Test schema loader."""

    def test_schemaLoader_returns_xmlschema_object(self):
        """Test Schemaloader return type is correct."""
        schema_name = "submission"
        schemaloader = SchemaLoader()
        schema = schemaloader.get_schema(schema_name)
        self.assertIs(type(schema), xmlschema.XMLSchema)

    def test_schemaLoader_raises_error_with_nonexistent_schema(self):
        """Test non-existent schemas is reported as error."""
        schema_name = "NULL"
        schemaloader = SchemaLoader()
        self.assertRaises(SchemaNotFoundException, schemaloader.get_schema,
                          schema_name)


if __name__ == '__main__':
    unittest.main()
