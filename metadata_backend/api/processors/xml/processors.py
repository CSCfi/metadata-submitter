"""Xml metadata object processor."""

# pylint: disable=too-many-lines

import os
from abc import ABC, abstractmethod
from itertools import chain
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable, Iterable, cast, override

import fsspec
from lxml import etree
from lxml.etree import QName
from lxml.etree import _Element as Element  # noqa
from lxml.etree import _ElementTree as ElementTree  # noqa

from metadata_backend.api.processors.xml.exceptions import SchemaValidationException
from metadata_backend.api.processors.xml.models import (
    XmlElementInsertionCallback,
    XmlObjectConfig,
    XmlObjectIdentifier,
    XmlObjectPaths,
    XmlReferencePaths,
    XmlSchemaPath,
    validate_absolute_path,
    validate_relative_path,
)

# TODO(improve): support name and accession references to existing metadata objects submitted by the same project
# TODO(improve): support accession references to existing metadata objects submitted by other projects
# TODO(improve): support setting FEGA @center_name and IDENTIFIERS/SUBMITTER_ID/@namespace

# XmlProcessor
#


class XmlProcessor(ABC):
    """Abstract base class for processing XML metadata objects."""

    @staticmethod
    def parse_xml(xml: str | bytes) -> ElementTree:
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

        # Indent with two spaces.
        return cast(str, etree.tostring(xml, pretty_print=True, encoding="unicode"))

    # Cache XML schemas.
    _xml_schema_cache: dict[str, etree.XMLSchema] = {}

    @staticmethod
    def validate_schema(
        xml: ElementTree | Element, schema_dir: str, schema_type: str, schema_file_resolver: Callable[[str], str]
    ) -> None:
        """
        Validate XML against XML Schema. Raise SchemaValidationException on failure.

        :param xml: XML element or element tree.
        :param schema_dir: The directory for the XML schema files.
        :param schema_type: The schema type must match the XML schema file name without the ".xsd" extension.
        :param schema_file_resolver: Resolves the schema file given the schema type.
        """
        xml_schema_file = schema_file_resolver(schema_type)
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

    @abstractmethod
    def get_xml_references_without_ids(self) -> list[XmlObjectIdentifier]:
        """
        Return metadata object references without ids.

        :return: metadata object references without ids.
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
        self._object_type = config.get_object_type(self.root_path)
        self._schema_type = config.get_schema_type(self._object_type)
        # Validate XML schema.
        if config.schema_dir is not None and config.schema_file_resolver is not None:
            self.validate_schema(xml, config.schema_dir, self._schema_type, self.config.schema_file_resolver)

        self.object_paths = self._get_object_paths()
        self.reference_paths = self._get_reference_paths()

        self._sync_identifiers()
        self._sync_ref_identifiers()

    def _sync_identifiers(self) -> None:
        """
        Check that the metadata object has a name and synchronise identifiers.

        Identifier synchronisation means that if multiple identifier paths exist
        they are changed to contain the same name and id.
        """
        if len(self.object_paths.identifier_paths) > 0:
            unique_name = set()
            unique_id = set()

            for p in self.object_paths.identifier_paths:
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
    def _normalise_xpath(path: str, prefix: str) -> str:
        """
        Normalise an XPath expression with the given prefix.

        :param path: Original XPath.
        :param prefix: Desired prefix for all steps (e.g., './' or '/').
        :return: Normalise XPath starting with the prefix.
        """
        path = path.strip()

        if not path.startswith("("):
            # Single path
            return prefix + path.lstrip(".").lstrip("/")

        # Multiple paths
        last = path.rfind(")")
        if last == -1:
            raise ValueError("Expected closing ')' in XPath")

        inner = path[1:last]
        post = path[last + 1 :]  # noqa

        # split by | and normalize each part
        parts = [prefix + p.strip().lstrip(".").lstrip("/") for p in inner.split("|")]
        return "(" + " | ".join(parts) + ")" + post

    @staticmethod
    def _get_absolute_xpath(path: str) -> str:
        """
        Return an absolute XPath.

        Ensures that paths in XPath start with '/'.

        param path: XPath.
        returns: Absolute XPath/
        """
        return XmlObjectProcessor._normalise_xpath(path, "/")

    @staticmethod
    def _get_relative_xpath(path: str) -> str:
        """
        Return a relative XPath.

        Ensures that paths in XPath start with './'.

        param path: XPath.
        returns: Relative XPath/
        """
        return XmlObjectProcessor._normalise_xpath(path, "./")

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
            validate_absolute_path(path)
        else:
            validate_relative_path(path)

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
            validate_absolute_path(path)
        else:
            validate_relative_path(path)

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
            validate_absolute_path(path)
        else:
            validate_relative_path(path)

        try:
            result = xml.xpath(path)
        except Exception as e:
            raise e

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

    def get_xml_node_value(self, path: str, *, optional: bool = False) -> str | None:
        """
        Retrieve the value of an XML element or attribute using a relative XPath expression.

        The XPath expression must be relative to the metadata object root element.

        :param path: XPath expression to locate the element or attribute.
        :param optional: If True, return None instead of raising if the node or value is missing.
        :return: The text or attribute value as a string, or None if optional and not found.
        """

        return self._get_xml_node_value(path, self.xml.getroot(), optional=optional)

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

        validate_relative_path(path)

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

    def _get_object_paths(self) -> XmlObjectPaths:
        """
        Retrieve the XML identifier path matching the current XML schema type and XML element.

        :return: XmlIdentifierPath corresponding to the XML schema type and XML element.
        """
        for path in self.config.object_paths:
            if path.schema_type == self._schema_type and path.root_path == self.root_path:
                return path

        raise ValueError(f"No identifier XPath found for schema '{self._schema_type}'")

    def _get_reference_paths(self) -> list[XmlReferencePaths]:
        """
        Retrieve the XML reference identifier paths matching the current XML schema type and XML element.

        :return: XmlReferenceIdentifierPaths corresponding to the XML schema type and XML element.
        """
        paths = []
        for path in self.config.reference_paths:
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
        name_path = self._get_relative_xpath(self.object_paths.identifier_paths[0].name_path)
        id_path = self._get_relative_xpath(self.object_paths.identifier_paths[0].id_path)
        return XmlObjectIdentifier(
            schema_type=self._schema_type,
            object_type=self._object_type,
            root_path=self.root_path,
            name=self._get_xml_node_value(name_path, self.root_element),
            id=self._get_xml_node_value(id_path, self.root_element, optional=True),
        )

    def _set_xml_object_name(self, value: str) -> None:
        """
        Set the metadata object name.

        :param value: The metadata object name.
        """
        for p in self.object_paths.identifier_paths:
            name_path = self._get_relative_xpath(p.name_path)
            self._set_xml_node_value(name_path, self.root_element, value, insertion_callback=p.name_insertion_callback)

    def set_xml_object_id(self, value: str) -> None:
        """
        Set the metadata object id.

        :param value: The metadata object id.
        """
        for p in self.object_paths.identifier_paths:
            id_path = self._get_relative_xpath(p.id_path)
            self._set_xml_node_value(id_path, self.root_element, value, insertion_callback=p.id_insertion_callback)

    @property
    def schema_type(self) -> str:
        """
        Retrieve the schema type.

        :return: schema type.
        """
        return self._schema_type

    @property
    def object_type(self) -> str:
        """
        Retrieve the metadata object type.

        :return: metadata object type.
        """
        return self._object_type

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
                        object_type=r.ref_object_type,
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

    @override
    def get_xml_references_without_ids(self) -> list[XmlObjectIdentifier]:
        """
        Return metadata object references without ids.

        :return: metadata object references without ids.
        """
        return [identifier for identifier in self.get_xml_object_references() if not identifier.id]

    def get_xml_object_title(self) -> str | None:
        """
        Retrieve the metadata object title.

        :return: metadata object title.
        """

        title_path = self.object_paths.title_path
        if title_path:
            title_path = self._get_relative_xpath(self.object_paths.title_path)
            return self._get_xml_node_value(title_path, self.root_element, optional=True)
        return None

    def get_xml_object_description(self) -> str | None:
        """
        Retrieve the metadata object description.

        :return: metadata object description.
        """

        description_path = self.object_paths.description_path
        if description_path:
            description_path = self._get_relative_xpath(self.object_paths.description_path)
            return self._get_xml_node_value(description_path, self.root_element, optional=True)
        return None


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

        self.config = config
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

        if self.xml_processors:
            schema_types = {p.schema_type for p in self.xml_processors}
            if len(schema_types) > 1:
                raise ValueError("All metadata objects in a document must have the same schema type")
            self._schema_type = next(iter(schema_types))

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
        root_path: str,
        name: str,
    ) -> bool:
        """
        Check if the metadata object processor exists.

        :param processors: The metadata object processors.
        :param schema_type: The schema type.
        :param root_path: The metadata object root path.
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
        root_path: str,
        name: str,
    ) -> XmlObjectProcessor:
        """
        Retrieve the metadata object processor.

        :param processors: The metadata object processors.
        :param schema_type: The schema type.
        :param root_path: The metadata object root path.
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

    def get_xml_object_identifier(self, schema_type: str, root_path: str, name: str) -> XmlObjectIdentifier:
        """
        Retrieve the metadata object identifier.

        :param schema_type: The schema type.
        :param root_path: The metadata object root path.
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
    def schema_type(self) -> str:
        """
        Retrieve the schema type.

        :return: the schema types.
        """
        return self._schema_type

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

    @override
    def get_xml_references_without_ids(self) -> list[XmlObjectIdentifier]:
        """
        Return metadata object references without ids.

        :return: metadata object references without ids.
        """
        return list(
            chain.from_iterable(processor.get_xml_references_without_ids() for processor in self.xml_processors)
        )

    @staticmethod
    async def write_xml_document(
        config: XmlObjectConfig,
        xmls: AsyncIterator[str] | str,
        writer: Callable[[bytes], Awaitable[None]],
        *,
        object_type: str | None = None,
        schema_type: str | None = None,
    ) -> None:
        """
        Stream XML document to an async writer.

        The XML document will start with an XML declaration and the
        XML metadata objects are wrapped inside the set element.

        Either object type or schema type must be provided.

        :param config: Configuration object for XML processing.
        :param xmls: Async XML iterator of XML strings or one XML string.
        :param writer: Async callable that accepts bytes.
        :param object_type: The object type.
        :param schema_type: The schema type.
        """
        if not (schema_type is not None) ^ (object_type is not None):
            raise ValueError("Either object type or schema type must be defined.")

        set_element = config.get_set_path(object_type=object_type, schema_type=schema_type).lstrip(".").lstrip("/")
        await writer(b"<?xml version='1.0' encoding='UTF-8'?>\n")
        await writer(f"<{set_element}>\n".encode("utf-8"))

        async def _write_indented(xml_: str) -> None:
            # Indent with two spaces.
            indented = "\n".join("  " + line for line in xml_.splitlines())
            if not indented.endswith("\n"):
                indented += "\n"
            await writer(indented.encode("utf-8"))

        if isinstance(xmls, str):
            await _write_indented(xmls)
        if isinstance(xmls, AsyncIterator):
            async for xml in xmls:
                await _write_indented(xml)

        await writer(f"</{set_element}>\n".encode("utf-8"))


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

        for o in config.object_paths:
            identifiers = self.get_xml_object_identifiers(o.schema_type)
            if o.is_single and o.is_mandatory:
                if len(identifiers) != 1:
                    raise ValueError(
                        f"Expecting exactly one '{o.schema_type}' metadata object but found {len(identifiers)}."
                    )
            elif o.is_mandatory:
                if len(identifiers) == 0:
                    raise ValueError(
                        f"Expecting at least one '{o.schema_type}' metadata object but found {len(identifiers)}."
                    )
            elif o.is_single:
                if len(identifiers) > 1:
                    raise ValueError(
                        f"Expecting at most one '{o.schema_type}' metadata object but found {len(identifiers)}."
                    )

    def get_xml_object_identifier(self, schema_type: str, root_path: str, name: str) -> XmlObjectIdentifier:
        """
        Retrieve the metadata object identifier.

        :param schema_type: The schema type.
        :param root_path: The metadata object root path.
        :param name: The unique metadata object name.
        :return: metadata object identifier.
        """

        return XmlDocumentProcessor.get_xml_object_processor(
            self.xml_processor, schema_type, root_path, name
        ).get_xml_object_identifier()

    def get_xml_object_processor(self, schema_type: str, root_path: str, name: str) -> XmlObjectProcessor:
        """
        Retrieve the metadata object identifier.

        :param schema_type: The schema type.
        :param root_path: The metadata object root path.
        :param name: The unique metadata object name.
        :return: metadata object identifier.
        """

        return XmlDocumentProcessor.get_xml_object_processor(self.xml_processor, schema_type, root_path, name)

    def get_xml_object_identifiers(self, schema_type: str | None = None) -> list[XmlObjectIdentifier]:
        """
        Retrieve the metadata object identifiers.

        :param schema_type: The schema type.
        :return: metadata object identifiers.
        """

        identifiers: list[XmlObjectIdentifier] = []
        for document_processor in self.xml_processors:
            for object_processor in document_processor.xml_processors:
                identifier = object_processor.get_xml_object_identifier()
                if schema_type is None or schema_type == identifier.schema_type:
                    identifiers.append(identifier)

        return identifiers

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

    @override
    def get_xml_references_without_ids(self) -> list[XmlObjectIdentifier]:
        """
        Return metadata object references without ids.

        :return: metadata object references without ids.
        """
        return list(
            chain.from_iterable(processor.get_xml_references_without_ids() for processor in self.xml_processors)
        )


class XmlStringDocumentsProcessor(XmlDocumentsProcessor):
    """Process one or more XML documents provided as strings."""

    def __init__(
        self,
        config: XmlObjectConfig,
        documents: list[str],
    ) -> None:
        """
        Process one or more XML documents provided as strings.

        :param config: Configuration object for XML processing.
        :param documents: List of XML document strings.
        """
        # Parse each string into an ElementTree
        xmls: list[ElementTree] = [XmlObjectProcessor.parse_xml(doc) for doc in documents]

        super().__init__(config, xmls)


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
        :param path: Path to the bucket with XML files.
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
