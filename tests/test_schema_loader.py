"""Tests for helper classes."""
import unittest

import xmlschema

from metadata_backend.helpers.schema_loader import (XMLSchemaLoader,
                                                    SchemaNotFoundException)


class TestXMLSchemaLoader(unittest.TestCase):
    """Test schema loader."""

    def test_XMLSchemaLoader_returns_xmlschema_object(self):
        """Test XMLSchemaLoader return type is correct."""
        schema_name = "submission"
        schemaloader = XMLSchemaLoader()
        schema = schemaloader.get_schema(schema_name)
        self.assertIs(type(schema), xmlschema.XMLSchema)

    def test_XMLSchemaLoader_raises_error_with_nonexistent_schema(self):
        """Test non-existent schemas is reported as error."""
        schema_name = "NULL"
        schemaloader = XMLSchemaLoader()
        self.assertRaises(SchemaNotFoundException, schemaloader.get_schema,
                          schema_name)


if __name__ == '__main__':
    unittest.main()
