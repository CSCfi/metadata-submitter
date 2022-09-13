"""Tests for helper classes."""
import unittest

import xmlschema

from metadata_backend.conf.conf import schema_types
from metadata_backend.helpers.schema_loader import (
    JSONSchemaLoader,
    SchemaNotFoundException,
    XMLSchemaLoader,
)


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


class TestAllDefinedSchemasExist(unittest.TestCase):
    """Test that all defined schemas exist."""

    def test_schemas_exist(self):
        """Test that all defined schemas have their schema definition."""
        schema_loader = JSONSchemaLoader()
        for schema_name in schema_types.keys():
            if schema_name in {"project", "datacite"}:
                continue
            schema = schema_loader.get_schema(schema_name)
            self.assertIs(type(schema), dict)


if __name__ == "__main__":
    unittest.main()
