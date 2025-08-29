"""Xml metadata object processor."""

# pylint: disable=too-many-lines

import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Iterable, Sequence, Type, cast, override

import fsspec
from lxml import etree
from lxml.etree import _LogEntry  # noqa
from lxml.etree import QName
from lxml.etree import _Element as Element  # noqa
from lxml.etree import _ElementTree as ElementTree
from pydantic import BaseModel, Field, field_validator

XML_SCHEMA_DIR = Path(__file__).parent.parent.parent / "helpers" / "schemas"
XML_ROOT_PATTERN = re.compile(r"^/[A-Za-z_][\w.-]*$")

# Callback to insert an XML element. Returns the inserted XML element.
XmlElementInsertionCallback = Callable[[Element], Element]


# TODO(improve): support name and accession references to existing metadata objects submitted by the same project
# TODO(improve): support accession references to existing metadata objects submitted by other projects
# TODO(improve): support setting FEGA @center_name and IDENTIFIERS/SUBMITTER_ID/@namespace

# Exceptions
#


class SchemaValidationException(Exception):
    """Exception containing XML Schema validation errors."""

    def __init__(self, schema_type: str, errors: Sequence[_LogEntry]) -> None:
        """
        Exception containing XML Schema validation errors.

        :param errors: Sequence or XML Schema validation errors.
        """
        self.errors: Sequence[_LogEntry] = errors
        messages: list[str] = [f"Line {err.line}: {err.message}" for err in errors]
        super().__init__(f"XML Schema validation failed for '{schema_type}':\n" + "\n".join(messages))


# Models
#


def _validate_absolute_path(path: str) -> str:
    if not path.startswith("/"):
        raise ValueError(f"XPath '{path}' expression must be absolute and and start with '/'")
    return path


def _validate_relative_path(path: str) -> str:
    if not path.startswith("."):
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
        return [_validate_absolute_path(path) for path in paths]


class XmlIdentifierPath(BaseModel):
    """Xml metadata object name and id XPath."""

    name_path: str  # Relative XPath to the name element or attribute.
    id_path: str  # Relative XPath to the id element or attribute.

    # Callback to insert name element. Relative to the identifier root path.
    name_insertion_callback: XmlElementInsertionCallback | None = None
    # Callback to insert id element. Relative to the identifier root path.
    id_insertion_callback: XmlElementInsertionCallback | None = None


class XmlIdentifierPaths(BaseModel):
    """Xml metadata object name and id XPaths."""

    schema_type: str
    root_path: str  # Absolute XPath to the metadata object root element.
    paths: list[XmlIdentifierPath] = Field(..., min_length=1)

    @field_validator("root_path", mode="before")
    @classmethod
    def validate_root_path(cls: Type["XmlIdentifierPaths"], path: str) -> str:
        """Validate XML root path.

        :param cls: The model class.
        :param path: Root path.
        :returns: The root path.
        """
        _ = cls  # silence vulture
        return _validate_absolute_path(path)


class XmlReferenceIdentifierPaths(BaseModel):
    """Xml metadata object reference name and id XPaths."""

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True

    schema_type: str  # The schema type having the reference.
    ref_schema_type: str  # The schema type being referenced.
    root_path: str  # Absolute XPath to the reference root element.
    paths: list[XmlIdentifierPath] = Field(..., min_length=1)  # XPaths relative to the reference root element.
    ref_root_path: str  # Absolute XPath to the root element being referenced.

    @field_validator("root_path", mode="before")
    @classmethod
    def validate_root_path(cls: Type["XmlReferenceIdentifierPaths"], path: str) -> str:
        """Validate XML root path.

        :param cls: The model class.
        :param path: Root path.
        :returns: The root path.
        """
        _ = cls  # silence vulture
        return _validate_absolute_path(path)

    @field_validator("ref_root_path", mode="before")
    @classmethod
    def validate_ref_root_path(cls: Type["XmlReferenceIdentifierPaths"], path: str) -> str:
        """Validate XML reference root path.

        :param cls: The model class.
        :param path: Reference root path.
        :returns: The reference root path.
        """
        _ = cls  # silence vulture
        return _validate_absolute_path(path)


class XmlObjectIdentifier(BaseModel):
    """Xml metadata object identifier with name and id."""

    schema_type: str  # The schema type.
    root_path: str  # Absolute XPath to the metadata object root element.
    name: str
    id: str | None


class XmlObjectConfig(BaseModel):
    """Xml metadata object schema and identifier configuration."""

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True

    # Directory containing XML Schema files. If specified, XML documents will be validated
    # against the corresponding schema. The schema type should match the XML schema file
    # name without the ".xsd" extension.
    schema_dir: str | None = None
    schema_paths: list[XmlSchemaPath]
    identifier_paths: list[XmlIdentifierPaths]
    ref_identifier_paths: list[XmlReferenceIdentifierPaths]


# XmlProcessor
#


class XmlProcessor(ABC):
    """Abstract base class for processing XML metadata objects."""

    @staticmethod
    def parse_xml(xml: str) -> ElementTree:
        """
        Parse XML string into an element tree with normalized whitespace.

        :param xml: XML string to parse.
        :return: XML element tree.
        """
        parser = etree.XMLParser(remove_blank_text=True, remove_comments=True)
        return etree.ElementTree(etree.fromstring(xml, parser))

    @staticmethod
    def write_xml(xml: ElementTree | Element) -> str:
        """
        Serialize XML to a pretty-printed string.

        :param xml: XML to serialize.
        :return: Pretty-printed XML string.
        """
        if isinstance(xml, ElementTree):
            xml = xml.getroot()

        return cast(str, etree.tostring(xml, pretty_print=True, encoding="unicode"))

    # Cache XML schemas.
    _xml_schema_cache: dict[str, etree.XMLSchema] = {}

    @staticmethod
    def validate_schema(xml: ElementTree | Element, schema_dir: str, schema_type: str) -> None:
        """
        Validate XML against XML Schema. Raise SchemaValidationException on failure.

        :param xml: XML element or element tree.
        :param schema_dir: The directory for the XML schema files.
        :param schema_type: The schema type must match the XML schema file name without the ".xsd" extension.
        """
        xml_schema_file = schema_type + ".xsd"
        xml_schema_path = os.path.join(schema_dir, xml_schema_file)

        # Cache XML schemas.
        if xml_schema_path not in XmlProcessor._xml_schema_cache:
            XmlProcessor._xml_schema_cache[xml_schema_path] = etree.XMLSchema(etree.parse(xml_schema_path))
        xml_schema = XmlProcessor._xml_schema_cache[xml_schema_path]

        if not xml_schema.validate(xml if isinstance(xml, ElementTree) else etree.ElementTree(xml)):
            raise SchemaValidationException(schema_type, xml_schema.error_log)

    @abstractmethod
    def get_xml_object_references(self) -> list[XmlObjectIdentifier]:
        """
        Retrieve the metadata object references.

        :return: The metadata object references.
        """

    @abstractmethod
    def set_xml_object_reference_ids(self, references: list[XmlObjectIdentifier]) -> None:
        """
        Set the metadata object reference ids.

        :param references: The metadata object references.
        """

    @abstractmethod
    def is_xml_object_reference_ids(self) -> bool:
        """
        Return true if all metadata object references in the XML have ids.

        :return: true if all metadata object references in the XML have ids.
        """


# XML processors
#


class XmlObjectProcessor(XmlProcessor):
    """
    Process one XML metadata object given an element tree.

    Automatically identifies the metadata type.
    """

    def __init__(self, config: XmlObjectConfig, xml: ElementTree) -> None:
        """
        Process one XML metadata object given an element tree.

        Automatically identifies the metadata type.

        :param config: Configuration object for XML processing.
        :param xml: XML element tree.
        """
        self.config = config
        self.xml = xml

        self.root_path = f"/{QName(xml.getroot().tag).localname}"
        self.root_element = self._get_xml_element(self.root_path, self.xml)

        def get_schema_type() -> str | None:
            for paths in self.config.schema_paths:
                for root_path in paths.root_paths:
                    if self.root_path == root_path:
                        return paths.schema_type
            return None

        self._schema_type = get_schema_type()
        if self._schema_type is None:
            raise ValueError("Unknown schema")

        # Validate XML schema.
        if config.schema_dir is not None:
            self.validate_schema(xml, config.schema_dir, self._schema_type)

        self.identifier_paths = self._get_identifier_paths()
        self.reference_paths = self._get_reference_paths()

        self._sync_identifiers()
        self._sync_ref_identifiers()

    def _sync_identifiers(self) -> None:
        """
        Check that the metadata object has a name and synchronise identifiers.

        Identifier synchronisation means that if multiple identifier paths exist
        they are changed to contain the same name and id.
        """
        if len(self.identifier_paths.paths) > 0:
            unique_name = set()
            unique_id = set()

            for p in self.identifier_paths.paths:
                name = self._get_xml_node_value(self._get_relative_xpath(p.name_path), self.root_element, optional=True)
                id_ = self._get_xml_node_value(self._get_relative_xpath(p.id_path), self.root_element, optional=True)
                if name:
                    unique_name.add(name)
                if id_:
                    unique_id.add(id_)

            if len(unique_name) == 0:
                raise ValueError("No metadata object name.")
            if len(unique_name) > 1:
                raise ValueError(f"Non-unique metadata object name: {", ".join(unique_name)}")
            if len(unique_id) > 1:
                raise ValueError(f"Non-unique metadata object id.: {", ".join(unique_id)}")

            if unique_name:
                self._set_xml_object_name(next(iter(unique_name)))
            if unique_id:
                self.set_xml_object_id(next(iter(unique_id)))

    def _sync_ref_identifiers(self) -> None:
        """
        Check that the metadata object references have a name and synchronise identifiers.

        Identifier synchronisation means that if multiple identifier paths exist
        they are changed to contain the same name and id.
        """
        for r in self.reference_paths:
            ref_path = self._get_absolute_xpath(r.root_path)
            ref_elements = self._get_xml_elements(ref_path, self.xml)
            for ref_element in ref_elements:
                ref_cnt = 0
                unique_name = set()
                unique_id = set()
                for p in r.paths:
                    name_path = self._get_relative_xpath(p.name_path)
                    id_path = self._get_relative_xpath(p.id_path)
                    name = self._get_xml_node_value(name_path, ref_element, optional=True)
                    id_ = self._get_xml_node_value(id_path, ref_element, optional=True)
                    if name or id_:
                        ref_cnt += 1
                    if name:
                        unique_name.add(name)
                    if id_:
                        unique_id.add(id_)

                if ref_cnt:
                    if len(unique_name) == 0:
                        raise ValueError("No metadata object reference name.")
                    if len(unique_name) > 1:
                        raise ValueError(f"Conflicting metadata object reference name: {", ".join(unique_name)}")
                    if len(unique_id) > 1:
                        raise ValueError(f"Conflicting metadata object reference id: {", ".join(unique_id)}")

                    for p in r.paths:
                        if unique_name:
                            name_path = self._get_relative_xpath(p.name_path)
                            self._set_xml_node_value(
                                name_path,
                                ref_element,
                                next(iter(unique_name)),
                                insertion_callback=p.name_insertion_callback,
                            )
                        if unique_id:
                            id_path = self._get_relative_xpath(p.id_path)
                            self._set_xml_node_value(
                                id_path, ref_element, next(iter(unique_id)), insertion_callback=p.id_insertion_callback
                            )

    @staticmethod
    def _get_absolute_xpath(*paths: str) -> str:
        """
        Combine root path and relative paths into a single absolute XPath.

        Each path is cleaned by removing leading '/' or './'.
        Ensures the result starts with '/'.

        param paths: Relative XPaths.

        returns: Absolute XPath starting with '/'.
        """

        parts = []
        for p in paths:
            parts.append(p.removeprefix(".").removeprefix("/"))
        return "/" + "/".join(parts)

    @staticmethod
    def _get_relative_xpath(*paths: str) -> str:
        """
        Combine root path and relative paths into a single relative XPath.

        Each path is cleaned by removing leading '/' or './'.
        Ensures the result starts with './'.

        param root_path: ROOT XPath.
        param paths: Relative XPaths.

        returns: Relative XPath starting with './'.
        """

        parts = []
        for p in paths:
            parts.append(p.removeprefix(".").removeprefix("/"))
        return "./" + "/".join(parts)

    @staticmethod
    def _get_xml_element(path: str, xml: ElementTree | Element, *, optional: bool = False) -> Element | None:
        """
        Retrieve the XML element using an XPath expression.

        :param path: XPath expression to locate the element.
        :param xml: XML element or element tree.
        :param optional: If True, return None instead of raising if the element is missing.
        :return: The XML element or None if optional and not found.
        """

        if isinstance(xml, ElementTree):
            _validate_absolute_path(path)
        else:
            _validate_relative_path(path)

        try:
            nodes = xml.xpath(path)
        except Exception as e:
            raise ValueError(f"Invalid XPath expression '{path}'") from e

        if nodes:
            if len(nodes) > 1:
                raise ValueError(f"More than on element found with XPath '{path}'")
            return nodes[0]

        if not optional:
            raise ValueError(f"Element with XPath '{path}' not found.")
        return None

    @staticmethod
    def _get_xml_elements(path: str, xml: ElementTree | Element) -> list[Element]:
        """
        Retrieve XML elements using an XPath expression.

        :param path: XPath expression to locate the elements.
        :param xml: XML element or element tree.
        :return: The XML elements.
        """

        if isinstance(xml, ElementTree):
            _validate_absolute_path(path)
        else:
            _validate_relative_path(path)

        try:
            nodes = xml.xpath(path)
        except Exception as e:
            raise ValueError(f"Invalid XPath expression '{path}'") from e

        if nodes:
            return cast(list[Element], nodes)
        return []

    @staticmethod
    def _get_xml_node_value(path: str, xml: ElementTree | Element, *, optional: bool = False) -> str | None:
        """
        Retrieve the value of an XML element or attribute using an XPath expression.

        The XPath expression must be absolute when the xml is an element tree and must start with /.
        The XPath expression must be relative when the xml is an element and must start with ./.

        :param path: XPath expression to locate the element or attribute.
        :param xml: XML element or element tree.
        :param optional: If True, return None instead of raising if the node or value is missing.
        :return: The text or attribute value as a string, or None if optional and not found.
        """
        if isinstance(xml, ElementTree):
            _validate_absolute_path(path)
        else:
            _validate_relative_path(path)

        result = xml.xpath(path)
        if not result:
            if optional:
                return None
            raise ValueError(f"XPath '{path}' not found.")

        value = result[0]
        if value is None:
            if optional:
                return None
            raise ValueError(f"XPath '{path}' value not found.")

        if isinstance(value, str):
            return value

        if isinstance(value, Element):
            if not value.text:
                if optional:
                    return None
                raise ValueError(f"XPath '{path}' value not found.")
            return cast(str, value.text)

        raise ValueError(f"XPath '{path}' unexpected type: {type(value).__name__}")

    @staticmethod
    def _set_xml_node_value(
        path: str, xml: Element, value: str, *, insertion_callback: XmlElementInsertionCallback | None
    ) -> None:
        """
        Set the value of an XML element or attribute specified by an XPath expression.

        Creates the element if it does not exist using an optional insertion callback.

        :param path: XPath expression identifying the target element or attribute relative to the XML element.
        :param xml: The XML element.
        :param value: Value to set on the target element or attribute.
        :param insertion_callback: Optional callback to insert a missing element when the XPath
                                   does not find the target node.
        """

        _validate_relative_path(path)

        parts = path.removeprefix(".").removeprefix("/").split("/")
        if len(parts) == 0:
            raise ValueError(f"XPath '{path}' does not point to any element or attribute.")

        # Check if target is an attribute
        last_part = parts[-1]
        is_attribute = last_part.startswith("@")

        def _get_node(
            _node_path: str,
            _parent_node: Element,
            _insertion_callback: XmlElementInsertionCallback | None,
        ) -> Element:
            try:
                _nodes = xml.xpath(_node_path)
            except Exception as e:
                raise ValueError(f"Invalid XPath expression '{path}'") from e
            if not _nodes:
                if _parent_node is not None and _insertion_callback is not None:
                    return _insertion_callback(_parent_node)
                raise ValueError(f"XPath '{path}' not found.")
            if len(_nodes) > 1:
                raise ValueError(f"XPath '{path}' matched multiple nodes.")
            return _nodes[0]

        if is_attribute:
            # Set attribute value. The element is expected to exist.
            attr_name = last_part[1:]  # remove '@'
            if len(parts) == 1:
                parent_element = xml
            else:
                parent_path = "./" + "/".join(parts[:-1])
                parent_element = XmlObjectProcessor._get_xml_element(parent_path, xml)
            parent_element.set(attr_name, value)
        else:
            # Set element value. The element is expected to be created by the inserting callback if it is missing.
            node = _get_node(path, xml, insertion_callback)
            node.text = value

    def _get_identifier_paths(self) -> XmlIdentifierPaths:
        """
        Retrieve the XML identifier path matching the current XML schema type and XML element.

        :return: XmlIdentifierPath corresponding to the XML schema type and XML element.
        """
        for path in self.config.identifier_paths:
            if path.schema_type == self._schema_type and path.root_path == self.root_path:
                return path

        raise ValueError(f"No identifier XPath found for schema '{self._schema_type}'")

    def _get_reference_paths(self) -> list[XmlReferenceIdentifierPaths]:
        """
        Retrieve the XML reference identifier paths matching the current XML schema type and XML element.

        :return: XmlReferenceIdentifierPaths corresponding to the XML schema type and XML element.
        """
        paths = []
        for path in self.config.ref_identifier_paths:
            if path.schema_type == self._schema_type and path.root_path.startswith(self.root_path):
                paths.append(path)
        return paths

    def get_xml_object_identifier(self) -> XmlObjectIdentifier:
        """
        Retrieve the metadata object identifier.

        :return: metadata object identifier.
        """

        # Extract the name and id from the first identifier path. If multiple identifier paths exist
        # they are guaranteed to contain the same information. This is done by synchronising the
        # identifiers when the XML metadata object processor is created, and always changing them together.
        name_path = self._get_relative_xpath(self.identifier_paths.paths[0].name_path)
        id_path = self._get_relative_xpath(self.identifier_paths.paths[0].id_path)
        return XmlObjectIdentifier(
            schema_type=self._schema_type,
            root_path=self.root_path,
            name=self._get_xml_node_value(name_path, self.root_element),
            id=self._get_xml_node_value(id_path, self.root_element, optional=True),
        )

    def _set_xml_object_name(self, value: str) -> None:
        """
        Set the metadata object name.

        :param value: The metadata object name.
        """
        for p in self.identifier_paths.paths:
            name_path = self._get_relative_xpath(p.name_path)
            self._set_xml_node_value(name_path, self.root_element, value, insertion_callback=p.name_insertion_callback)

    def set_xml_object_id(self, value: str) -> None:
        """
        Set the metadata object id.

        :param value: The metadata object id.
        """
        for p in self.identifier_paths.paths:
            id_path = self._get_relative_xpath(p.id_path)
            self._set_xml_node_value(id_path, self.root_element, value, insertion_callback=p.id_insertion_callback)

    @property
    def schema_type(self) -> str:
        """
        Retrieve the metadata object schema type.

        :return: metadata object schema type.
        """
        return self._schema_type

    @override
    def get_xml_object_references(self) -> list[XmlObjectIdentifier]:
        """
        Retrieve the metadata object references.

        :return: The metadata object references.
        """
        references = []
        for r in self.reference_paths:
            ref_path = self._get_absolute_xpath(r.root_path)
            ref_elements = self._get_xml_elements(ref_path, self.xml)
            for ref_element in ref_elements:
                # Extract the name and id from the first reference identifier path. If multiple
                # reference identifier paths exist they are guaranteed to contain the same information.
                # This is done by synchronising the reference identifiers when the XML metadata object
                # processor is created, and always changing them together.
                p = r.paths[0]
                name_path = self._get_relative_xpath(p.name_path)
                id_path = self._get_relative_xpath(p.id_path)
                references.append(
                    XmlObjectIdentifier(
                        schema_type=r.ref_schema_type,
                        root_path=r.ref_root_path,
                        name=self._get_xml_node_value(name_path, ref_element),
                        id=self._get_xml_node_value(id_path, ref_element, optional=True),
                    )
                )
        return references

    @override
    def set_xml_object_reference_ids(self, references: list[XmlObjectIdentifier]) -> None:
        """
        Set the metadata object reference ids.

        :param references: The metadata object references.
        """

        def _find_reference(schema_type_: str, root_path_: str, name_: str) -> XmlObjectIdentifier | None:
            # Find matching input reference.
            for ref in references:
                if ref.schema_type == schema_type_ and ref.root_path == root_path_ and ref.name == name_:
                    return ref
            return None

        # Extract all references from the XML.
        for r in self.reference_paths:
            ref_path = self._get_absolute_xpath(r.root_path)
            ref_elements = self._get_xml_elements(ref_path, self.xml)
            for ref_element in ref_elements:
                for p in r.paths:
                    # Extract reference name.
                    name_path = self._get_relative_xpath(p.name_path)
                    name = self._get_xml_node_value(name_path, ref_element)
                    # Find matching input reference.
                    reference = _find_reference(r.ref_schema_type, r.ref_root_path, name)
                    if reference and reference.id:
                        id_path = self._get_relative_xpath(p.id_path)
                        self._set_xml_node_value(
                            id_path, ref_element, reference.id, insertion_callback=p.id_insertion_callback
                        )

    @override
    def is_xml_object_reference_ids(self) -> bool:
        """
        Return true if all metadata object references in the XML have ids.

        :return: true if all metadata object references in the XML have ids.
        """

        return all(ref.id for ref in self.get_xml_object_references())


class XmlDocumentProcessor(XmlProcessor):
    """
    Process one or more XML metadata objects given a root element.

    Automatically identifies the metadata type.
    """

    def __init__(self, config: XmlObjectConfig, xml: ElementTree) -> None:
        """
        Process one or more XML metadata objects given an element tree.

        Automatically identifies the metadata type.

        :param config: Configuration object for XML processing.
        :param xml: XML element tree.
        """

        self.xml = xml
        # Xml object processors.
        self.xml_processors: list[XmlObjectProcessor] = []
        # Xml object processor by schema, root tag and name.
        self.xml_processor: dict[str, dict[str, dict[str, XmlObjectProcessor]]] = {}

        found_set_path = next((p.set_path for p in config.schema_paths if xml.xpath(p.set_path)), None)

        if found_set_path:
            # Multiple objects.
            for set_xml in xml.xpath(found_set_path):
                for _xml in set_xml:
                    self._add_xml_processor(config, etree.ElementTree(_xml))
        else:
            # Single object.
            self._add_xml_processor(config, xml)

        self._schema_types = list({p.schema_type for p in self.xml_processors})

    def _add_xml_processor(self, config: XmlObjectConfig, xml: ElementTree) -> None:
        """
        Add an XML processor.

        :param config: Configuration object for XML processing.
        :param xml: XML element tree.
        """
        p = XmlObjectProcessor(config, xml)
        self.xml_processors.append(p)

        # Check if we already have metadata object processors for the same names.
        name = p.get_xml_object_identifier().name
        if self.is_xml_object_processor(self.xml_processor, p.schema_type, p.root_path, name):
            raise ValueError(f"Duplicate '{p.schema_type}' identifier '{name}'")
        self.set_xml_object_processor(self.xml_processor, name, p)

    @staticmethod
    def is_xml_object_processor(
        processors: dict[str, dict[str, dict[str, XmlObjectProcessor]]],
        schema_type: str,
        root_path: str | None,
        name: str,
    ) -> bool:
        """
        Check if the metadata object processor exists.

        :param processors: The metadata object processors.
        :param schema_type: The schema type.
        :param root_path: The metadata object root path. Required if the XML schema
            contains multiple metadata object types.
        :param name: The unique metadata object name.
        :return: metadata object processor.
        """
        if not processors.get(schema_type):
            return False
        if not processors[schema_type].get(root_path):
            return False
        if not processors[schema_type][root_path].get(name):
            return False
        return True

    @staticmethod
    def get_xml_object_processor(
        processors: dict[str, dict[str, dict[str, XmlObjectProcessor]]],
        schema_type: str,
        root_path: str | None,
        name: str,
    ) -> XmlObjectProcessor:
        """
        Retrieve the metadata object processor.

        :param processors: The metadata object processors.
        :param schema_type: The schema type.
        :param root_path: The metadata object root path. Required if the XML schema
            contains multiple metadata object types.
        :param name: The unique metadata object name.
        :return: metadata object processor.
        """
        schema_type_map = processors.get(schema_type)
        if not schema_type_map:
            raise ValueError(f"Unknown schema '{schema_type}'.")

        root_path_map = schema_type_map.get(root_path)
        if not root_path_map:
            raise ValueError(f"Unknown '{schema_type}' path '{root_path}'.")

        processor = root_path_map.get(name)

        if not processor:
            if root_path:
                raise ValueError(f"Unknown '{schema_type}' path '{root_path}' name '{name}'.")
            raise ValueError(f"Unknown '{schema_type}' name '{name}'.")

        return processor

    @staticmethod
    def set_xml_object_processor(
        processors: dict[str, dict[str, dict[str, XmlObjectProcessor]]], name: str, processor: XmlObjectProcessor
    ) -> None:
        """
        Set the metadata object processor.

        :param processors: The metadata object processors.
        :param name: The unique metadata object name.
        :param processor: metadata object processor.
        """
        schema_type = processor.schema_type
        root_path = processor.root_path
        processors.setdefault(schema_type, {})
        processors[schema_type].setdefault(root_path, {})
        processors[schema_type][root_path][name] = processor

    def get_xml_object_identifier(self, schema_type: str, root_path: str | None, name: str) -> XmlObjectIdentifier:
        """
        Retrieve the metadata object identifier.

        :param schema_type: The schema type.
        :param root_path: The metadata object root path. Required if the XML schema
            contains multiple metadata object types.
        :param name: The unique metadata object name.
        :return: metadata object identifier.
        """
        return self.get_xml_object_processor(
            self.xml_processor, schema_type, root_path, name
        ).get_xml_object_identifier()

    def set_xml_object_id(self, identifier: XmlObjectIdentifier) -> None:
        """
        Set the metadata object id.

        :param identifier: The metadata object identifier that must have the id. If the XML schema
        supports multiple metadata object types then must also have the root path.
        """
        schema_type = identifier.schema_type
        root_path = identifier.root_path
        name = identifier.name
        id_ = identifier.id

        if not identifier.id:
            raise ValueError(f"Missing id for '{schema_type}' name '{name}'.")

        self.get_xml_object_processor(self.xml_processor, schema_type, root_path, name).set_xml_object_id(id_)

    @property
    def schema_types(self) -> list[str]:
        """
        Retrieve the metadata object schema types.

        :return: metadata object schema types.
        """
        return self._schema_types

    @override
    def get_xml_object_references(self) -> list[XmlObjectIdentifier]:
        """
        Retrieve the metadata object references.

        :return: The metadata object references.
        """
        references = []
        for processor in self.xml_processors:
            references.extend(processor.get_xml_object_references())
        return references

    @override
    def set_xml_object_reference_ids(self, references: list[XmlObjectIdentifier]) -> None:
        """
        Set the metadata object reference ids.

        :param references: The metadata object references.
        """
        for processor in self.xml_processors:
            processor.set_xml_object_reference_ids(references)

    @override
    def is_xml_object_reference_ids(self) -> bool:
        """
        Return true if all metadata object references in the XML have ids.

        :return: true if all metadata object references in the XML have ids.
        """
        return all(processor.is_xml_object_reference_ids() for processor in self.xml_processors)


class XmlDocumentsProcessor(XmlProcessor):
    """Process one or more XML documents objects given their root elements."""

    def __init__(self, config: XmlObjectConfig, xml: ElementTree | Iterable[ElementTree]) -> None:
        """
        Process one or more XML documents objects given their element trees.

        :param config: Configuration object for XML processing.
        :param xml: XML element trees.
        """

        if isinstance(xml, ElementTree):
            self.xmls = [xml]
        elif isinstance(xml, Iterable):
            self.xmls = list(xml)
        else:
            raise TypeError("Xml must be a single or iterable of ElementTree")

        # Xml document processors.
        self.xml_processors: list[XmlDocumentProcessor] = []
        # Xml object processor by scheme, root path and name.
        self.xml_processor: dict[str, dict[str, dict[str, XmlObjectProcessor]]] = {}

        for _xml in self.xmls:
            processor = XmlDocumentProcessor(config, _xml)
            self.xml_processors.append(processor)

            # Check if we already have metadata object processors for the same names.
            for p in processor.xml_processors:
                name = p.get_xml_object_identifier().name
                if XmlDocumentProcessor.is_xml_object_processor(self.xml_processor, p.schema_type, p.root_path, name):
                    raise ValueError(f"Duplicate '{p.schema_type}' identifier '{name}'")
                XmlDocumentProcessor.set_xml_object_processor(self.xml_processor, name, p)

    def get_xml_object_identifier(self, schema_type: str, root_path: str | None, name: str) -> XmlObjectIdentifier:
        """
        Retrieve the metadata object identifier.

        :param schema_type: The schema type.
        :param root_path: The metadata object root path. Required if the XML schema
            contains multiple metadata object types.
        :param name: The unique metadata object name.
        :return: metadata object identifier.
        """

        return XmlDocumentProcessor.get_xml_object_processor(
            self.xml_processor, schema_type, root_path, name
        ).get_xml_object_identifier()

    def set_xml_object_id(self, identifier: XmlObjectIdentifier) -> None:
        """
        Set the metadata object id.

        :param identifier: The metadata object identifier that must have the id. If the XML schema
        supports multiple metadata object types then must also have the root path.
        """
        schema_type = identifier.schema_type
        root_path = identifier.root_path
        name = identifier.name
        id_ = identifier.id

        if not identifier.id:
            raise ValueError(f"Missing id for '{schema_type}' name '{name}'.")

        XmlDocumentProcessor.get_xml_object_processor(
            self.xml_processor, schema_type, root_path, name
        ).set_xml_object_id(id_)
        self.set_xml_object_reference_ids([identifier])

    @override
    def get_xml_object_references(self) -> list[XmlObjectIdentifier]:
        """
        Retrieve the metadata object references.

        :return: The metadata object references.
        """
        references = []
        for processor in self.xml_processors:
            references.extend(processor.get_xml_object_references())
        return references

    @override
    def set_xml_object_reference_ids(self, references: list[XmlObjectIdentifier]) -> None:
        """
        Set the metadata object reference ids.

        :param references: The metadata object references.
        """
        for processor in self.xml_processors:
            processor.set_xml_object_reference_ids(references)

    @override
    def is_xml_object_reference_ids(self) -> bool:
        """
        Return true if all metadata object references in the XML have ids.

        :return: true if all metadata object references in the XML have ids.
        """
        return all(processor.is_xml_object_reference_ids() for processor in self.xml_processors)


class XmlFileDocumentsProcessor(XmlDocumentsProcessor):
    """Process one or more XML files."""

    def __init__(
        self,
        config: XmlObjectConfig,
        path: str | Path,
        whitelist: list[str | Path] | None = None,
        fs: fsspec.AbstractFileSystem | None = None,
    ) -> None:
        """
        Process one or more XML files.

        :param config: Configuration object for XML processing.
        :param path: Path to the folder with XML files.
        :param whitelist: If provided, only these XML files are read.
            Otherwise, all `.xml` files are read recursively.
            Assumes that relative paths are used.
        :param fs: fsspec filesystem instance. Defaults to local filesystem.
        """

        if isinstance(path, str):
            path = Path(path)
        whitelist = [Path(p) for p in whitelist]
        fs = fs or fsspec.filesystem("file")

        xmls: list[ElementTree] = []

        if whitelist:
            # Read whitelisted files using relative paths.
            for rel_path in whitelist:
                file_path = path / rel_path
                if fs.exists(str(file_path)):
                    with fs.open(str(file_path), "r", encoding="utf-8") as f:
                        xmls.append(XmlObjectProcessor.parse_xml(f.read()))
        else:
            # Read all .xml files recursively.
            for file_path in fs.find(str(path)):
                if file_path.endswith(".xml"):
                    with fs.open(file_path, "r", encoding="utf-8") as f:
                        xmls.append(XmlObjectProcessor.parse_xml(f.read()))

        super().__init__(config, xmls)


def _xml_schema_path(schema_type: str, root_paths: str | list[str], set_path: str) -> XmlSchemaPath:
    if isinstance(root_paths, str):
        root_paths = [root_paths]
    return XmlSchemaPath(set_path=set_path, schema_type=schema_type, root_paths=root_paths)


# BP
#

# The schema type must match the XML schema file name without the ".xsd" extension.

BP_ANNOTATION_SCHEMA = "BP.bpannotation"
BP_DATASET_SCHEMA = "BP.bpdataset"
BP_IMAGE_SCHEMA = "BP.bpimage"
BP_LANDING_PAGE_SCHEMA = "BP.bplandingpage"
BP_OBSERVATION_SCHEMA = "BP.bpobservation"
BP_OBSERVER_SCHEMA = "BP.bpobserver"
BP_ORGANISATION_SCHEMA = "BP.bporganisation"
BP_POLICY_SCHEMA = "BP.bppolicy"
BP_REMS_SCHEMA = "BP.bprems"
BP_SAMPLE_SCHEMA = "BP.bpsample"
BP_STAINING_SCHEMA = "BP.bpstaining"

BP_ANNOTATION_PATH = "/ANNOTATION"
BP_DATASET_PATH = "/DATASET"
BP_IMAGE_PATH = "/IMAGE"
BP_LANDING_PAGE_PATH = "/LANDING_PAGE"
BP_OBSERVATION_PATH = "/OBSERVATION"
BP_OBSERVER_PATH = "/OBSERVER"
BP_ORGANISATION_PATH = "/ORGANISATION"
BP_POLICY_PATH = "/POLICY"
BP_REMS_PATH = "/REMS"
BP_SAMPLE_BIOLOGICAL_BEING_PATH = "/BIOLOGICAL_BEING"
BP_SAMPLE_SLIDE_PATH = "/SLIDE"
BP_SAMPLE_SPECIMEN_PATH = "/SPECIMEN"
BP_SAMPLE_BLOCK_PATH = "/BLOCK"
BP_SAMPLE_CASE_PATH = "/CASE"
BP_STAINING_PATH = "/STAINING"

BP_ANNOTATION_SCHEMA_AND_PATH = (BP_ANNOTATION_SCHEMA, BP_ANNOTATION_PATH)
BP_DATASET_SCHEMA_AND_PATH = (BP_DATASET_SCHEMA, BP_DATASET_PATH)
BP_IMAGE_SCHEMA_AND_PATH = (BP_IMAGE_SCHEMA, BP_IMAGE_PATH)
BP_LANDING_PAGE_SCHEMA_AND_PATH = (BP_LANDING_PAGE_SCHEMA, BP_LANDING_PAGE_PATH)
BP_OBSERVATION_SCHEMA_AND_PATH = (BP_OBSERVATION_SCHEMA, BP_OBSERVATION_PATH)
BP_OBSERVER_SCHEMA_AND_PATH = (BP_OBSERVER_SCHEMA, BP_OBSERVER_PATH)
BP_ORGANISATION_SCHEMA_AND_PATH = (BP_ORGANISATION_SCHEMA, BP_ORGANISATION_PATH)
BP_POLICY_SCHEMA_AND_PATH = (BP_POLICY_SCHEMA, BP_POLICY_PATH)
BP_REMS_SCHEMA_AND_PATH = (BP_REMS_SCHEMA, BP_REMS_PATH)
BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH = (BP_SAMPLE_SCHEMA, BP_SAMPLE_BIOLOGICAL_BEING_PATH)
BP_SAMPLE_SLIDE_SCHEMA_AND_PATH = (BP_SAMPLE_SCHEMA, BP_SAMPLE_SLIDE_PATH)
BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH = (BP_SAMPLE_SCHEMA, BP_SAMPLE_SPECIMEN_PATH)
BP_SAMPLE_BLOCK_SCHEMA_AND_PATH = (BP_SAMPLE_SCHEMA, BP_SAMPLE_BLOCK_PATH)
BP_SAMPLE_CASE_SCHEMA_AND_PATH = (BP_SAMPLE_SCHEMA, BP_SAMPLE_CASE_PATH)
BP_STAINING_SCHEMA_AND_PATH = (BP_STAINING_SCHEMA, BP_STAINING_PATH)

BP_ANNOTATION_SET_PATH = "/ANNOTATION_SET"
BP_DATASET_SET_PATH = "/DATASET_SET"
BP_IMAGE_SET_PATH = "/IMAGE_SET"
BP_LANDING_PAGE_SET_PATH = "/LANDING_PAGE_SET"
BP_OBSERVATION_SET_PATH = "/OBSERVATION_SET"
BP_OBSERVER_SET_PATH = "/OBSERVER_SET"
BP_ORGANISATION_SET_PATH = "/ORGANISATION_SET"
BP_POLICY_SET_PATH = "/POLICY_SET"
BP_REMS_SET_PATH = "/REMS_SET"
BP_SAMPLE_SET_PATH = "/SAMPLE_SET"
BP_STAINING_SET_PATH = "/STAINING_SET"


def _xml_identifier_path_bp(schema_type: str, root_path: str) -> XmlIdentifierPaths:
    return XmlIdentifierPaths(
        schema_type=schema_type,
        root_path=root_path,
        paths=[XmlIdentifierPath(id_path="/@accession", name_path="/@alias")],
    )


def _xml_ref_path_bp(
    schema_type: str, root_path: str, rel_ref_path: str, ref_schema_type: str, ref_root_path: str
) -> XmlReferenceIdentifierPaths:
    return XmlReferenceIdentifierPaths(
        schema_type=schema_type,
        ref_schema_type=ref_schema_type,
        root_path=root_path + "/" + rel_ref_path,
        ref_root_path=ref_root_path,
        paths=[XmlIdentifierPath(id_path="@accession", name_path="@alias")],
    )


BP_XML_OBJECT_CONFIG = XmlObjectConfig(
    schema_dir=str(XML_SCHEMA_DIR),
    schema_paths=[
        _xml_schema_path(*BP_ANNOTATION_SCHEMA_AND_PATH, BP_ANNOTATION_SET_PATH),
        _xml_schema_path(*BP_DATASET_SCHEMA_AND_PATH, BP_DATASET_SET_PATH),
        _xml_schema_path(*BP_IMAGE_SCHEMA_AND_PATH, BP_IMAGE_SET_PATH),
        _xml_schema_path(*BP_LANDING_PAGE_SCHEMA_AND_PATH, BP_LANDING_PAGE_SET_PATH),
        _xml_schema_path(*BP_OBSERVATION_SCHEMA_AND_PATH, BP_OBSERVATION_SET_PATH),
        _xml_schema_path(*BP_OBSERVER_SCHEMA_AND_PATH, BP_OBSERVER_SET_PATH),
        _xml_schema_path(*BP_ORGANISATION_SCHEMA_AND_PATH, BP_ORGANISATION_SET_PATH),
        _xml_schema_path(*BP_POLICY_SCHEMA_AND_PATH, BP_POLICY_SET_PATH),
        _xml_schema_path(*BP_REMS_SCHEMA_AND_PATH, BP_REMS_SET_PATH),
        _xml_schema_path(
            BP_SAMPLE_SCHEMA,
            [
                BP_SAMPLE_BIOLOGICAL_BEING_PATH,
                BP_SAMPLE_SLIDE_PATH,
                BP_SAMPLE_SPECIMEN_PATH,
                BP_SAMPLE_BLOCK_PATH,
                BP_SAMPLE_CASE_PATH,
            ],
            BP_SAMPLE_SET_PATH,
        ),
        _xml_schema_path(*BP_STAINING_SCHEMA_AND_PATH, BP_STAINING_SET_PATH),
    ],
    identifier_paths=[
        _xml_identifier_path_bp(*BP_ANNOTATION_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_DATASET_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_IMAGE_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_LANDING_PAGE_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_OBSERVER_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_ORGANISATION_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_POLICY_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_REMS_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_SAMPLE_SLIDE_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_SAMPLE_BLOCK_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_SAMPLE_CASE_SCHEMA_AND_PATH),
        _xml_identifier_path_bp(*BP_STAINING_SCHEMA_AND_PATH),
    ],
    ref_identifier_paths=[
        # annotation
        _xml_ref_path_bp(*BP_ANNOTATION_SCHEMA_AND_PATH, "/IMAGE_REF", *BP_IMAGE_SCHEMA_AND_PATH),
        # dataset
        _xml_ref_path_bp(*BP_DATASET_SCHEMA_AND_PATH, "/IMAGE_REF", *BP_IMAGE_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_DATASET_SCHEMA_AND_PATH, "/ANNOTATION_REF", *BP_ANNOTATION_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_DATASET_SCHEMA_AND_PATH, "/OBSERVATION_REF", *BP_OBSERVATION_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_DATASET_SCHEMA_AND_PATH, "/COMPLEMENTS_DATASET_REF", *BP_DATASET_SCHEMA_AND_PATH),
        # image
        _xml_ref_path_bp(*BP_IMAGE_SCHEMA_AND_PATH, "/IMAGE_OF", *BP_SAMPLE_SLIDE_SCHEMA_AND_PATH),
        # observation
        _xml_ref_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH, "/ANNOTATION_REF", *BP_ANNOTATION_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH, "/CASE_REF", *BP_SAMPLE_CASE_SCHEMA_AND_PATH),
        _xml_ref_path_bp(
            *BP_OBSERVATION_SCHEMA_AND_PATH, "/BIOLOGICAL_BEING_REF", *BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH
        ),
        _xml_ref_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH, "/SPECIMEN_REF", *BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH, "/BLOCK_REF", *BP_SAMPLE_BLOCK_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH, "/SLIDE_REF", *BP_SAMPLE_SLIDE_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH, "/IMAGE_REF", *BP_IMAGE_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_OBSERVATION_SCHEMA_AND_PATH, "/OBSERVER_REF", *BP_OBSERVER_SCHEMA_AND_PATH),
        # organisation
        _xml_ref_path_bp(*BP_ORGANISATION_SCHEMA_AND_PATH, "/DATASET_REF", *BP_DATASET_SCHEMA_AND_PATH),
        # policy
        _xml_ref_path_bp(*BP_POLICY_SCHEMA_AND_PATH, "/DATASET_REF", *BP_DATASET_SCHEMA_AND_PATH),
        # rems
        _xml_ref_path_bp(*BP_REMS_SCHEMA_AND_PATH, "/DATASET_REF", *BP_DATASET_SCHEMA_AND_PATH),
        # landing page
        _xml_ref_path_bp(*BP_LANDING_PAGE_SCHEMA_AND_PATH, "/DATASET_REF", *BP_DATASET_SCHEMA_AND_PATH),
        # sample
        _xml_ref_path_bp(*BP_SAMPLE_SLIDE_SCHEMA_AND_PATH, "/STAINING_INFORMATION_REF", *BP_STAINING_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_SAMPLE_SLIDE_SCHEMA_AND_PATH, "/CREATED_FROM_REF", *BP_SAMPLE_BLOCK_SCHEMA_AND_PATH),
        _xml_ref_path_bp(
            *BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH, "/EXTRACTED_FROM_REF", *BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH
        ),
        _xml_ref_path_bp(*BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH, "/PART_OF_CASE_REF", *BP_SAMPLE_CASE_SCHEMA_AND_PATH),
        _xml_ref_path_bp(*BP_SAMPLE_BLOCK_SCHEMA_AND_PATH, "/SAMPLED_FROM_REF", *BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH),
        _xml_ref_path_bp(
            *BP_SAMPLE_CASE_SCHEMA_AND_PATH, "/BIOLOGICAL_BEING_REF", *BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH
        ),
    ],
)

# FEGA
#

# The schema type must match the XML schema file name without the ".xsd" extension.

FEGA_DAC_SCHEMA = "EGA.dac"
FEGA_DATASET_SCHEMA = "EGA.dataset"
FEGA_ANALYSIS_SCHEMA = "SRA.analysis"
FEGA_EXPERIMENT_SCHEMA = "SRA.experiment"
FEGA_RUN_SCHEMA = "SRA.run"
FEGA_SAMPLE_SCHEMA = "SRA.sample"
FEGA_STUDY_SCHEMA = "SRA.study"
FEGA_POLICY_SCHEMA = "EGA.policy"
FEGA_SUBMISSION_SCHEMA = "SRA.submission"

FEGA_DAC_PATH = "/DAC"
FEGA_DATASET_PATH = "/DATASET"
FEGA_ANALYSIS_PATH = "/ANALYSIS"
FEGA_EXPERIMENT_PATH = "/EXPERIMENT"
FEGA_RUN_PATH = "/RUN"
FEGA_SAMPLE_PATH = "/SAMPLE"
FEGA_STUDY_PATH = "/STUDY"
FEGA_POLICY_PATH = "/POLICY"
FEGA_SUBMISSION_PATH = "/SUBMISSION"

FEGA_DAC_SCHEMA_AND_PATH = (FEGA_DAC_SCHEMA, FEGA_DAC_PATH)
FEGA_DATASET_SCHEMA_AND_PATH = (FEGA_DATASET_SCHEMA, FEGA_DATASET_PATH)
FEGA_ANALYSIS_SCHEMA_AND_PATH = (FEGA_ANALYSIS_SCHEMA, FEGA_ANALYSIS_PATH)
FEGA_EXPERIMENT_SCHEMA_AND_PATH = (FEGA_EXPERIMENT_SCHEMA, FEGA_EXPERIMENT_PATH)
FEGA_RUN_SCHEMA_AND_PATH = (FEGA_RUN_SCHEMA, FEGA_RUN_PATH)
FEGA_SAMPLE_SCHEMA_AND_PATH = (FEGA_SAMPLE_SCHEMA, FEGA_SAMPLE_PATH)
FEGA_STUDY_SCHEMA_AND_PATH = (FEGA_STUDY_SCHEMA, FEGA_STUDY_PATH)
FEGA_POLICY_SCHEMA_AND_PATH = (FEGA_POLICY_SCHEMA, FEGA_POLICY_PATH)
FEGA_SUBMISSION_SCHEMA_AND_PATH = (FEGA_SUBMISSION_SCHEMA, FEGA_SUBMISSION_PATH)

FEGA_DAC_SET_PATH = "/DAC_SET"
FEGA_DATASET_SET_PATH = "/DATASETS"
FEGA_ANALYSIS_SET_PATH = "/ANALYSIS_SET"
FEGA_EXPERIMENT_SET_PATH = "/EXPERIMENT_SET"
FEGA_RUN_SET_PATH = "/RUN_SET"
FEGA_SAMPLE_SET_PATH = "/SAMPLE_SET"
FEGA_STUDY_SET_PATH = "/STUDY_SET"
FEGA_POLICY_SET_PATH = "/POLICY_SET"
FEGA_SUBMISSION_SET_PATH = "/SUBMISSION_SET"


def _id_insertion_callback_fega(node: Element) -> Element:
    # Add IDENTIFIERS element as the first element.
    identifiers_element = node.find("IDENTIFIERS")
    if identifiers_element is None:
        identifiers_element = etree.Element("IDENTIFIERS")
        node.insert(0, identifiers_element)
    # Add PRIMARY_ID element as the first element.
    primary_id_element = identifiers_element.find("PRIMARY_ID")
    if primary_id_element is None:
        primary_id_element = etree.Element("PRIMARY_ID")
        identifiers_element.insert(0, primary_id_element)
    return primary_id_element


def _name_insertion_callback_fega(node: Element) -> Element:
    # Add IDENTIFIERS element as the first element.
    identifiers_element = node.find("IDENTIFIERS")
    if identifiers_element is None:
        identifiers_element = etree.Element("IDENTIFIERS")
        node.insert(0, identifiers_element)
    # Add SUBMITTER_ID element as the first child element of IDENTIFIERS element
    # after EXTERNAL_ID if it exists, or after SECONDARY_ID if it exists, or after
    # PRIMARY_ID if it exists. Otherwise, add it as the first element.

    submitter_id_element = etree.Element("SUBMITTER_ID")

    inserted = False
    for insert_after_element_name in ["EXTERNAL_ID", "SECONDARY_ID", "PRIMARY_ID"]:
        insert_after_element = identifiers_element.find(insert_after_element_name)
        if insert_after_element is not None:
            index = identifiers_element.index(insert_after_element)
            identifiers_element.insert(index + 1, submitter_id_element)
            inserted = True
            break
    if not inserted:
        identifiers_element.insert(0, submitter_id_element)

    return submitter_id_element


def _xml_identifier_path_fega(schema_type: str, root_path: str) -> XmlIdentifierPaths:
    return XmlIdentifierPaths(
        schema_type=schema_type,
        root_path=root_path,
        paths=[
            XmlIdentifierPath(id_path="/@accession", name_path="/@alias"),
            XmlIdentifierPath(
                id_path="IDENTIFIERS/PRIMARY_ID",
                name_path="IDENTIFIERS/SUBMITTER_ID",
                id_insertion_callback=_id_insertion_callback_fega,
                name_insertion_callback=_name_insertion_callback_fega,
            ),
        ],
    )


def _xml_ref_path_fega(
    schema_type: str, root_path: str, rel_ref_path: str, ref_schema_type: str, ref_root_path: str
) -> XmlReferenceIdentifierPaths:
    return XmlReferenceIdentifierPaths(
        schema_type=schema_type,
        ref_schema_type=ref_schema_type,
        root_path=root_path + "/" + rel_ref_path,
        ref_root_path=ref_root_path,
        paths=[
            XmlIdentifierPath(id_path="@accession", name_path="@refname"),
            XmlIdentifierPath(
                id_path="@IDENTIFIERS/PRIMARY_ID",
                name_path="IDENTIFIERS/SUBMITTER_ID",
                id_insertion_callback=_id_insertion_callback_fega,
                name_insertion_callback=_name_insertion_callback_fega,
            ),
        ],
    )


FEGA_XML_OBJECT_CONFIG = XmlObjectConfig(
    schema_dir=str(XML_SCHEMA_DIR),
    schema_paths=[
        _xml_schema_path(*FEGA_DAC_SCHEMA_AND_PATH, FEGA_DAC_SET_PATH),
        _xml_schema_path(*FEGA_DATASET_SCHEMA_AND_PATH, FEGA_DATASET_SET_PATH),
        _xml_schema_path(*FEGA_ANALYSIS_SCHEMA_AND_PATH, FEGA_ANALYSIS_SET_PATH),
        _xml_schema_path(*FEGA_EXPERIMENT_SCHEMA_AND_PATH, FEGA_EXPERIMENT_SET_PATH),
        _xml_schema_path(*FEGA_RUN_SCHEMA_AND_PATH, FEGA_RUN_SET_PATH),
        _xml_schema_path(*FEGA_SAMPLE_SCHEMA_AND_PATH, FEGA_SAMPLE_SET_PATH),
        _xml_schema_path(*FEGA_STUDY_SCHEMA_AND_PATH, FEGA_STUDY_SET_PATH),
        _xml_schema_path(*FEGA_POLICY_SCHEMA_AND_PATH, FEGA_POLICY_SET_PATH),
        _xml_schema_path(*FEGA_SUBMISSION_SCHEMA_AND_PATH, FEGA_SUBMISSION_SET_PATH),
    ],
    identifier_paths=[
        _xml_identifier_path_fega(*FEGA_DAC_SCHEMA_AND_PATH),
        _xml_identifier_path_fega(*FEGA_DATASET_SCHEMA_AND_PATH),
        _xml_identifier_path_fega(*FEGA_ANALYSIS_SCHEMA_AND_PATH),
        _xml_identifier_path_fega(*FEGA_EXPERIMENT_SCHEMA_AND_PATH),
        _xml_identifier_path_fega(*FEGA_RUN_SCHEMA_AND_PATH),
        _xml_identifier_path_fega(*FEGA_SAMPLE_SCHEMA_AND_PATH),
        _xml_identifier_path_fega(*FEGA_STUDY_SCHEMA_AND_PATH),
        _xml_identifier_path_fega(*FEGA_POLICY_SCHEMA_AND_PATH),
        _xml_identifier_path_fega(*FEGA_SUBMISSION_SCHEMA_AND_PATH),
    ],
    ref_identifier_paths=[
        # DAC
        # dataset
        _xml_ref_path_fega(*FEGA_DATASET_SCHEMA_AND_PATH, "RUN_REF", *FEGA_RUN_SCHEMA_AND_PATH),
        _xml_ref_path_fega(*FEGA_DATASET_SCHEMA_AND_PATH, "ANALYSIS_REF", *FEGA_ANALYSIS_SCHEMA_AND_PATH),
        _xml_ref_path_fega(*FEGA_DATASET_SCHEMA_AND_PATH, "POLICY_REF", *FEGA_POLICY_SCHEMA_AND_PATH),
        # analysis
        _xml_ref_path_fega(*FEGA_ANALYSIS_SCHEMA_AND_PATH, "STUDY_REF", *FEGA_STUDY_SCHEMA_AND_PATH),
        _xml_ref_path_fega(*FEGA_ANALYSIS_SCHEMA_AND_PATH, "SAMPLE_REF", *FEGA_SAMPLE_SCHEMA_AND_PATH),
        _xml_ref_path_fega(*FEGA_ANALYSIS_SCHEMA_AND_PATH, "EXPERIMENT_REF", *FEGA_EXPERIMENT_SCHEMA_AND_PATH),
        _xml_ref_path_fega(*FEGA_ANALYSIS_SCHEMA_AND_PATH, "RUN_REF", *FEGA_RUN_SCHEMA_AND_PATH),
        _xml_ref_path_fega(*FEGA_ANALYSIS_SCHEMA_AND_PATH, "ANALYSIS_REF", *FEGA_ANALYSIS_SCHEMA_AND_PATH),
        # experiment
        _xml_ref_path_fega(*FEGA_EXPERIMENT_SCHEMA_AND_PATH, "STUDY_REF", *FEGA_STUDY_SCHEMA_AND_PATH),
        _xml_ref_path_fega(*FEGA_EXPERIMENT_SCHEMA_AND_PATH, "DESIGN/SAMPLE_DESCRIPTOR", *FEGA_SAMPLE_SCHEMA_AND_PATH),
        # run
        _xml_ref_path_fega(*FEGA_RUN_SCHEMA_AND_PATH, "EXPERIMENT_REF", *FEGA_EXPERIMENT_SCHEMA_AND_PATH),
        # sample
        # study
        # policy
        _xml_ref_path_fega(*FEGA_POLICY_SCHEMA_AND_PATH, "DAC_REF", *FEGA_DAC_SCHEMA_AND_PATH),
        # submission
    ],
)
