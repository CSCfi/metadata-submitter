"""Test the schema loading utility."""
import unittest

import xmlschema

from metadata_backend.helpers.schema_loader import JSONSchemaLoader, SchemaNotFoundException, XMLSchemaLoader


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
        self.assertRaises(SchemaNotFoundException, schemaloader.get_schema, schema_name)


class TestJSONSchemaLoader(unittest.TestCase):
    """Test schema loader."""

    def test_JSONSchemaLoader_returns_xmlschema_object(self):
        """Test JSONSchemaLoader return type is correct."""
        schema_name = "study"
        schemaloader = JSONSchemaLoader()
        schema = schemaloader.get_schema(schema_name)
        self.assertIs(type(schema), dict)

    def test_JSONSchemaLoader_raises_error_with_nonexistent_schema(self):
        """Test non-existent schemas is reported as error."""
        schema_name = "NULL"
        schemaloader = JSONSchemaLoader()
        self.assertRaises(SchemaNotFoundException, schemaloader.get_schema, schema_name)


if __name__ == "__main__":
    unittest.main()
