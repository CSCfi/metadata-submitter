import unittest
import xmlschema

from pathlib import Path
from metadata_backend.schema_load import SchemaLoader
from metadata_backend.logger import LOG

TESTFILES_ROOT = Path(__file__).parent / 'test_files'


class TestUtilClasses(unittest.TestCase):
    """
    Test utility classes and their methods
    """

    def setUp(self):
        """Initialise fixtures."""
        pass

    def tearDown(self):
        """Remove setup variables."""
        pass

    def test_schemaLoader_returns_xmlschema_object(self):
        """Test Schemaloader return type."""
        schema_name = "submission"
        schemaloader = SchemaLoader()
        schema = schemaloader.get_schema(schema_name)
        self.assertIs(type(schema), xmlschema.XMLSchema)

    def test_schemaLoader_raises_error_with_invalid_schema(self):
        schema_name = "NULL"
        schemaloader = SchemaLoader()
        self.assertRaises(ValueError, schemaloader.get_schema,
                          schema_name)


if __name__ == '__main__':
    unittest.main()
