"""
This utility class validates xmlfiles against xsd files

"""
from metadata_backend.logger import LOG


class XMLValidator():
    """Handles validation of xml strings against xsd schemas"""
    def __init__(self):
        pass

    @staticmethod
    def validate(xml_content, schema_name, schema_loader):
        """
        Validates xml string against schema found with schema_name.

        :param xml_content: xml to be validated
        :param schame_name: schema used for validation
        :param schema_loader: SchemaLoader-object which used to access xsd
        schemas
        """
        try:
            schema = schema_loader.get_schema(schema_name)
        except ValueError as error:
            LOG.info("Not able to find schema with given name,"
                     f"Error message: {error}")
            return False
        return schema.is_valid(xml_content)
