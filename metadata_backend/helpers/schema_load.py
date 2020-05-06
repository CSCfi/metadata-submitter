"""Schema loader.

This utility class will find XSD Schema that can be used to test xml files. Can
be used via get_schema-method.

Current implementation relies on search schemas from folder with xsd files

"""

from pathlib import Path

import xmlschema

from ..helpers.logger import LOG

SCHEMAS_ROOT = Path(__file__).parent / 'schemas'


class SchemaLoader():
    """Loader implementations"""

    def __init__(self):
        """Load schemas folder on initialization"""
        self.path = SCHEMAS_ROOT

    def get_schema(self, schema_name):
        """
        Gets xmlschema-object which can be used to match xml files againts
        schema.

        xmlschema-documentation: https://xmlschema.readthedocs.io/en/latest/

        :param schema_name: Name of the schema
        :returns: XMLSchema-object
        :raises ValueError: If schema with schema_name doesn't exist
        """
        schema_name = schema_name.lower()
        schema_file = None
        for file in [x for x in self.path.iterdir()]:
            if schema_name in file.name:
                with file.open() as f:
                    schema_file = f.read()
        if not schema_file:
            reason = "There is no xsd file for given schema"
            LOG.info(f"Error: {reason}")
            raise ValueError(reason)
        schema = xmlschema.XMLSchema(schema_file,
                                     base_url=self.path.as_posix())
        return schema
