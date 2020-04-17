"""
This utility class validates xmlfiles against xsd files
"""

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
        except ValueError:
            # LOG error here
            return False 
        return schema.is_valid(xml_content) 
