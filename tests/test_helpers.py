import unittest

import xmlschema
from metadata_backend.helpers.schema_load import (SchemaLoader,
                                                  SchemaNotFoundException)


class TestUtilClasses(unittest.TestCase):
    """
    Test helper classes and their methods.
    """

    def test_schemaLoader_returns_xmlschema_object(self):
        """Test Schemaloader return type."""
        schema_name = "submission"
        schemaloader = SchemaLoader()
        schema = schemaloader.get_schema(schema_name)
        self.assertIs(type(schema), xmlschema.XMLSchema)

    def test_schemaLoader_raises_error_with_nonexistent_schema(self):
        schema_name = "NULL"
        schemaloader = SchemaLoader()
        self.assertRaises(SchemaNotFoundException, schemaloader.get_schema,
                          schema_name)


if __name__ == '__main__':
    unittest.main()
