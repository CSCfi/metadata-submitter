"""
This utility class validates XML files against xsd files
"""

from xml.etree.ElementTree import ParseError
from ..helpers.logger import LOG


class XMLValidator:
    """Handles validation of xml strings against xsd schemas"""
    def __init__(self):
        pass

    @staticmethod
    def validate(xml_content, schema_name, schema_loader):
        """
        Validates xml string against schema found with schema_name.

        :param xml_content: xml to be validated
        :param schema_name: schema used for validation
        :param schema_loader: SchemaLoader-object which used to access xsd
        schemas
        :raises ValueError: If schema with schema_name doesn't exist
        """
        try:
            schema = schema_loader.get_schema(schema_name)
        except ValueError as error:
            raise error
        try:
            is_valid = schema.is_valid(xml_content)
        except ParseError as error:
            LOG.info(f"Error when parsing xml file: {error}")
            is_valid = False
        return is_valid
