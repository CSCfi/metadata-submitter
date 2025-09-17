"""Xml metadata object processor."""

from typing import Callable, Type

from lxml.etree import _Element as Element  # noqa
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Callback to insert an XML element. Returns the inserted XML element.
XmlElementInsertionCallback = Callable[[Element], Element]


# Models
#


def validate_absolute_path(path: str) -> str:
    """
    Validate absolute XPATH.

    :param path: The XPATH.
    :return: The XPATH.
    """
    if not path.startswith("/"):
        raise ValueError(f"XPath '{path}' expression must be absolute and and start with '/'")
    return path


def validate_relative_path(path: str) -> str:
    """
    Validate relative XPATH.

    :param path: The XPATH.
    :return: The XPATH.
    """
    if not path.startswith(".") and not path.startswith("(."):
        raise ValueError(f"XPath '{path}' expression must be relative and and start with '.'")
    return path


class XmlSchemaPath(BaseModel):
    """Xml metadata object schema given an identifying XPath."""

    schema_type: str
    # Root path for multiple metadata objects. If not given, one metadata object is expected.
    set_path: str | None = None
    # Absolute XPaths to the root elements of metadata objects. May be nested inside the optional root
    # path for multiple metadata objects.
    root_paths: list[str]

    @field_validator("root_paths", mode="before")
    @classmethod
    def validate_root_paths(cls: Type["XmlSchemaPath"], paths: list[str]) -> list[str]:
        """Validate XML root paths.

        :param cls: The model class.
        :param paths: List of root paths.
        :returns: List of root paths.
        """
        _ = cls  # silence vulture
        return [validate_absolute_path(path) for path in paths]


class XmlIdentifierPath(BaseModel):
    """Xml metadata object name and id XPath."""

    name_path: str  # Relative XPath to the name element or attribute.
    id_path: str  # Relative XPath to the id element or attribute.

    # Callback to insert name element. Relative to the identifier root path.
    name_insertion_callback: XmlElementInsertionCallback | None = None
    # Callback to insert id element. Relative to the identifier root path.
    id_insertion_callback: XmlElementInsertionCallback | None = None


class XmlObjectPaths(BaseModel):
    """Xml metadata object XPaths."""

    schema_type: str
    object_type: str
    root_path: str  # Absolute XPath to the metadata object root element.
    is_mandatory: bool = False
    is_single: bool = False
    identifier_paths: list[XmlIdentifierPath] = Field(..., min_length=1)
    title_path: str | None = None  # Relative XPath to the title.
    description_path: str | None = None  # Relative XPath to the description.

    @field_validator("root_path", mode="before")
    @classmethod
    def validate_root_path(cls: Type["XmlObjectPaths"], path: str) -> str:
        """Validate XML root path.

        :param cls: The model class.
        :param path: Root path.
        :returns: The root path.
        """
        _ = cls  # silence vulture
        return validate_absolute_path(path)


class XmlReferencePaths(BaseModel):
    """Xml metadata object reference XPaths."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    schema_type: str  # The schema type having the reference.
    object_type: str  # The object type having the reference.
    ref_schema_type: str  # The schema type being referenced.
    ref_object_type: str  # The object type being referenced.
    root_path: str  # Absolute XPath to the reference root element.
    ref_root_path: str  # Absolute XPath to the root element being referenced.
    paths: list[XmlIdentifierPath] = Field(..., min_length=1)  # XPaths relative to the reference root element.

    @field_validator("root_path", mode="before")
    @classmethod
    def validate_root_path(cls: Type["XmlReferencePaths"], path: str) -> str:
        """Validate XML root path.

        :param cls: The model class.
        :param path: Root path.
        :returns: The root path.
        """
        _ = cls  # silence vulture
        return validate_absolute_path(path)

    @field_validator("ref_root_path", mode="before")
    @classmethod
    def validate_ref_root_path(cls: Type["XmlReferencePaths"], path: str) -> str:
        """Validate XML reference root path.

        :param cls: The model class.
        :param path: Reference root path.
        :returns: The reference root path.
        """
        _ = cls  # silence vulture
        return validate_absolute_path(path)


class XmlObjectIdentifier(BaseModel):
    """Xml metadata object identifier with name and id."""

    schema_type: str
    object_type: str
    root_path: str  # Absolute XPath to the metadata object root element.
    name: str
    id: str | None


class XmlObjectConfig(BaseModel):
    """Xml metadata object schema and identifier configuration."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    schema_paths: list[XmlSchemaPath]
    object_paths: list[XmlObjectPaths]
    reference_paths: list[XmlReferencePaths]

    # Directory containing XML Schema files. If specified, XML documents will be validated
    # against the corresponding schema. The schema type should match the XML schema file
    # name without the ".xsd" extension.
    schema_dir: str | None = None
    schema_file_resolver: Callable[[str], str] | None = None

    def get_root_path(self, object_type: str) -> str:
        """
        Get the root path for the metadata object.

        :param object_type: The object type.
        :return: The root path for the metadata object.
        """

        for p in self.object_paths:
            if p.object_type == object_type:
                return p.root_path

        raise ValueError(f"Unknown object type: {object_type}")

    def get_set_path(self, *, object_type: str | None = None, schema_type: str | None = None) -> str | None:
        """
        Get the root path for multiple metadata objects.

        Either object type or schema type must be provided.

        :param object_type: The object type.
        :param schema_type: The schema type.
        :return: The root path for multiple metadata objects.
        """
        if not (schema_type is not None) ^ (object_type is not None):
            raise ValueError("Either object type or schema type must be defined.")

        def get_set_path(schema_type_: str) -> str | None:
            for o_ in self.schema_paths:
                if o_.schema_type == schema_type_:
                    return o_.set_path
            return None

        if schema_type is not None:
            return get_set_path(schema_type)

        for o in self.object_paths:
            if o.object_type == object_type:
                return get_set_path(o.schema_type)

        return None

    def get_object_type(self, root_path: str) -> str:
        """
        Get the object type for a metadata object root path.

        :param root_path: The metadata object root path.
        :return: The object type.
        """
        for p in self.object_paths:
            if p.root_path == root_path:
                return p.object_type

        raise ValueError(f"Unknown object type for root path: {root_path}")

    def get_schema_type(self, object_type: str) -> str | None:
        """
        Get the schema type for a metadata object type.

        :param object_type: The metadata object type.
        :return: The schema type.
        """
        for p in self.object_paths:
            if p.object_type == object_type:
                return p.schema_type

        raise ValueError(f"Unknown schema type for object type: {object_type}")

    def get_object_types(self, schema_type: str) -> list[str]:
        """
        Get the object types for a schema type.

        :param schema_type: The schema type
        :return: The object types.
        """
        object_types = []
        for p in self.object_paths:
            if p.schema_type == schema_type:
                object_types.append(p.object_type)

        if not object_types:
            raise ValueError(f"Unknown object type for schema type : {schema_type}")

        return object_types
