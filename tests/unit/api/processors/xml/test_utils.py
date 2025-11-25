import uuid
from pathlib import Path

import pytest
from lxml import etree
from lxml.etree import _Element as Element  # noqa

from metadata_backend.api.processors.models import ObjectIdentifier
from metadata_backend.api.processors.xml.models import (
    XmlIdentifierPath,
    XmlObjectConfig,
    XmlObjectPaths,
    XmlReferencePaths,
    XmlSchemaPath,
)
from metadata_backend.api.processors.xml.processors import (
    XmlDocumentProcessor,
    XmlDocumentsProcessor,
    XmlObjectProcessor,
)

TEST_FILES_DIR = Path(__file__).parent.parent.parent.parent.parent / "test_files"


def assert_xml(expected, actual):
    print(etree.tostring(actual, pretty_print=True, encoding="unicode"))
    assert etree.tostring(expected, pretty_print=True, encoding="unicode") == etree.tostring(
        actual, pretty_print=True, encoding="unicode"
    )


async def test_with_element_existing():
    name = f"{str(uuid.uuid4())}"
    ref_name_1 = f"{str(uuid.uuid4())}"
    ref_name_2 = f"{str(uuid.uuid4())}"
    title = f"{str(uuid.uuid4())}"
    description = f"{str(uuid.uuid4())}"

    xml_str = f"""
    <Test>
      <Name>{name}</Name>
      <ID></ID>
      <References>
        <Reference>
          <name>{ref_name_1}</name>
          <id></id>
        </Reference>
        <Reference>
          <name>{ref_name_2}</name>
          <id></id>
        </Reference>
      </References>
      <Title>{title}</Title>
      <Description>{description}</Description>
    </Test>
    """

    schema_type = "test_schema_type"
    object_type = "test_object_type"
    root_path = "/Test"
    ref_schema_type = "test_ref_schema_type"
    ref_object_type = "test_ref_object_type"
    ref_root_path = "/RefTest"
    title_path = "/Title"
    description_path = "/Description"

    config = XmlObjectConfig(
        schema_paths=[XmlSchemaPath(schema_type=schema_type, root_paths=[root_path])],
        object_paths=[
            XmlObjectPaths(
                schema_type=schema_type,
                object_type=object_type,
                root_path=root_path,
                identifier_paths=[XmlIdentifierPath(name_path="Name", id_path="ID")],
                title_path=title_path,
                description_path=description_path,
            ),
        ],
        reference_paths=[
            XmlReferencePaths(
                schema_type=schema_type,
                ref_schema_type=ref_schema_type,
                object_type=object_type,
                ref_object_type=ref_object_type,
                root_path="/Test/References/Reference",
                paths=[XmlIdentifierPath(id_path="id", name_path="name")],
                ref_root_path=ref_root_path,
            )
        ],
    )

    # Test configuration
    assert config.get_root_path(object_type) == root_path
    assert config.get_object_type(root_path) == object_type
    assert config.get_schema_type(object_type) == schema_type
    assert config.get_object_types(schema_type) == [object_type]

    xml = XmlObjectProcessor.parse_xml(xml_str)
    processor = XmlObjectProcessor(config, xml)

    # Get schema and object type
    assert processor.schema_type == schema_type
    assert processor.object_type == object_type

    # Get name and id
    assert processor.get_xml_object_identifier().name == name
    assert processor.get_xml_object_identifier().id is None

    # Get title and description
    assert processor.get_object_title() == title
    assert processor.get_object_description() == description

    # Set id
    id = f"{str(uuid.uuid4())}"
    processor.set_xml_object_id(id)
    assert processor.get_xml_object_identifier().name == name
    assert processor.get_xml_object_identifier().id == id

    # Get references
    refs = processor.get_object_references()
    assert len(refs) == 2
    assert refs[0].name == ref_name_1
    assert refs[0].id is None
    assert refs[0].schema_type == ref_schema_type
    assert refs[0].object_type == ref_object_type
    assert refs[1].name == ref_name_2
    assert refs[1].id is None
    assert refs[1].schema_type == ref_schema_type
    assert refs[1].object_type == ref_object_type

    # Set reference ids
    ref_id_1 = f"{str(uuid.uuid4())}"
    ref_id_2 = f"{str(uuid.uuid4())}"
    ref_1 = ObjectIdentifier(
        schema_type=ref_schema_type, object_type=ref_object_type, root_path=ref_root_path, name=ref_name_1, id=ref_id_1
    )
    ref_2 = ObjectIdentifier(
        schema_type=ref_schema_type, object_type=ref_object_type, root_path=ref_root_path, name=ref_name_2, id=ref_id_2
    )
    updated_refs = [ref_1, ref_2]
    processor.set_object_reference_ids(updated_refs)
    refs = processor.get_object_references()

    assert len(refs) == 2
    assert ref_1 in refs
    assert ref_2 in refs

    # Check reference ids
    assert processor.is_object_reference_ids()

    # Check XML

    expected_xml_str = f"""
        <Test>
          <Name>{name}</Name>
          <ID>{id}</ID>
          <References>
            <Reference>
              <name>{ref_name_1}</name>
              <id>{ref_id_1}</id>
           </Reference>
            <Reference>
              <name>{ref_name_2}</name>
              <id>{ref_id_2}</id>
            </Reference>
          </References>
          <Title>{title}</Title>
          <Description>{description}</Description>
        </Test>
        """

    assert_xml(XmlObjectProcessor.parse_xml(expected_xml_str), xml)


async def test_with_id_element_missing():
    name = f"{str(uuid.uuid4())}"
    ref_name_1 = f"{str(uuid.uuid4())}"
    ref_name_2 = f"{str(uuid.uuid4())}"

    xml_str = f"""
    <Test>
      <Name>{name}</Name>
      <References>
        <Reference>
          <name>{ref_name_1}</name>
        </Reference>
        <Reference>
          <name>{ref_name_2}</name>
        </Reference>
      </References>
    </Test>
    """

    schema_type = "test_schema_type"
    object_type = "test_object_type"
    root_path = "/Test"
    ref_schema_type = "test_ref_schema_type"
    ref_object_type = "test_ref_object_type"
    ref_root_path = "/RefTest"

    def id_insertion_callback(node: Element):
        # Add ID node into a specific place in the XML.
        name_node = node.find("Name")
        if name_node is None:
            raise ValueError("'Name' element not found")
        id_node = etree.Element("ID")
        node.insert(list(node).index(name_node) + 1, id_node)
        return id_node

    config = XmlObjectConfig(
        schema_paths=[XmlSchemaPath(schema_type=schema_type, root_paths=[root_path])],
        object_paths=[
            XmlObjectPaths(
                schema_type=schema_type,
                object_type=object_type,
                root_path=root_path,
                identifier_paths=[
                    XmlIdentifierPath(name_path="Name", id_path="ID", id_insertion_callback=id_insertion_callback)
                ],
            )
        ],
        reference_paths=[
            XmlReferencePaths(
                schema_type=schema_type,
                ref_schema_type=ref_schema_type,
                object_type=object_type,
                ref_object_type=ref_object_type,
                root_path="/Test/References/Reference",
                paths=[
                    XmlIdentifierPath(
                        id_path="id", name_path="name", id_insertion_callback=lambda node: etree.SubElement(node, "id")
                    )
                ],
                ref_root_path=ref_root_path,
            )
        ],
    )

    xml = XmlObjectProcessor.parse_xml(xml_str)
    processor = XmlObjectProcessor(config, xml)

    # Get schema type
    assert processor.schema_type == schema_type

    # Get name and id
    assert processor.get_xml_object_identifier().name == name
    assert processor.get_xml_object_identifier().id is None

    # Set id
    id = f"{str(uuid.uuid4())}"
    processor.set_xml_object_id(id)
    assert processor.get_xml_object_identifier().name == name
    assert processor.get_xml_object_identifier().id == id

    # Get references
    refs = processor.get_object_references()
    assert len(refs) == 2
    assert refs[0].name == ref_name_1
    assert refs[0].id is None
    assert refs[0].schema_type == ref_schema_type
    assert refs[0].object_type == ref_object_type
    assert refs[1].name == ref_name_2
    assert refs[1].id is None
    assert refs[1].schema_type == ref_schema_type
    assert refs[1].object_type == ref_object_type

    # Set reference ids
    ref_id_1 = f"{str(uuid.uuid4())}"
    ref_id_2 = f"{str(uuid.uuid4())}"
    ref_1 = ObjectIdentifier(
        schema_type=ref_schema_type, object_type=ref_object_type, root_path=ref_root_path, name=ref_name_1, id=ref_id_1
    )
    ref_2 = ObjectIdentifier(
        schema_type=ref_schema_type, object_type=ref_object_type, root_path=ref_root_path, name=ref_name_2, id=ref_id_2
    )
    updated_refs = [ref_1, ref_2]
    processor.set_object_reference_ids(updated_refs)
    refs = processor.get_object_references()

    assert len(refs) == 2
    assert ref_1 in refs
    assert ref_2 in refs

    # Check reference ids
    assert processor.is_object_reference_ids()

    # Check XML

    expected_xml_str = f"""
        <Test>
          <Name>{name}</Name>
          <ID>{id}</ID>
          <References>
            <Reference>
              <name>{ref_name_1}</name>
              <id>{ref_id_1}</id>
           </Reference>
            <Reference>
              <name>{ref_name_2}</name>
              <id>{ref_id_2}</id>
            </Reference>
          </References>
        </Test>
        """

    assert_xml(XmlObjectProcessor.parse_xml(expected_xml_str), xml)


async def test_with_attribute():
    name = f"{str(uuid.uuid4())}"
    ref_name_1 = f"{str(uuid.uuid4())}"
    ref_name_2 = f"{str(uuid.uuid4())}"
    title = f"{str(uuid.uuid4())}"
    description = f"{str(uuid.uuid4())}"

    xml_str = f"""
    <Test title="{title}" description="{description}">
      <Identifier name="{name}"/>
      <References>
        <Reference name="{ref_name_1}"/>
        <Reference name="{ref_name_2}"/>
      </References>
    </Test>
    """

    schema_type = "test_schema_type"
    object_type = "test_object_type"
    root_path = "/Test"
    ref_schema_type = "test_ref_schema_type"
    ref_object_type = "test_ref_object_type"
    ref_root_path = "/RefTest"
    title_path = "@title"
    description_path = "@description"

    config = XmlObjectConfig(
        schema_paths=[XmlSchemaPath(schema_type=schema_type, root_paths=[root_path])],
        object_paths=[
            XmlObjectPaths(
                schema_type=schema_type,
                object_type=object_type,
                root_path=root_path,
                identifier_paths=[XmlIdentifierPath(name_path="Identifier/@name", id_path="Identifier/@id")],
                title_path=title_path,
                description_path=description_path,
            )
        ],
        reference_paths=[
            XmlReferencePaths(
                schema_type=schema_type,
                ref_schema_type=ref_schema_type,
                object_type=object_type,
                ref_object_type=ref_object_type,
                root_path="/Test/References/Reference",
                paths=[XmlIdentifierPath(id_path="@id", name_path="@name")],
                ref_root_path=ref_root_path,
            )
        ],
    )

    xml = XmlObjectProcessor.parse_xml(xml_str)
    processor = XmlObjectProcessor(config, xml)

    # Get schema type
    assert processor.schema_type == schema_type

    # Get name and id
    assert processor.get_xml_object_identifier().name == name
    assert processor.get_xml_object_identifier().id is None

    # Get title and description
    assert processor.get_object_title() == title
    assert processor.get_object_description() == description

    # Set id
    id = f"{str(uuid.uuid4())}"
    processor.set_xml_object_id(id)
    assert processor.get_xml_object_identifier().name == name
    assert processor.get_xml_object_identifier().id == id

    # Get references
    refs = processor.get_object_references()
    assert len(refs) == 2
    assert refs[0].name == ref_name_1
    assert refs[0].id is None
    assert refs[0].schema_type == ref_schema_type
    assert refs[0].object_type == ref_object_type
    assert refs[1].name == ref_name_2
    assert refs[1].id is None
    assert refs[1].schema_type == ref_schema_type
    assert refs[1].object_type == ref_object_type

    # Set reference ids
    ref_id_1 = f"{str(uuid.uuid4())}"
    ref_id_2 = f"{str(uuid.uuid4())}"
    ref_1 = ObjectIdentifier(
        schema_type=ref_schema_type, object_type=ref_object_type, root_path=ref_root_path, name=ref_name_1, id=ref_id_1
    )
    ref_2 = ObjectIdentifier(
        schema_type=ref_schema_type, object_type=ref_object_type, root_path=ref_root_path, name=ref_name_2, id=ref_id_2
    )
    updated_refs = [ref_1, ref_2]
    processor.set_object_reference_ids(updated_refs)
    refs = processor.get_object_references()

    assert len(refs) == 2
    assert ref_1 in refs
    assert ref_2 in refs

    # Check reference ids
    assert processor.is_object_reference_ids()

    # Check XML

    expected_xml_str = f"""
        <Test title="{title}" description="{description}">
          <Identifier name="{name}" id="{id}"/>
          <References>
            <Reference name="{ref_name_1}" id="{ref_id_1}"/>
            <Reference name="{ref_name_2}" id="{ref_id_2}"/>
          </References>
        </Test>
    """

    assert_xml(XmlObjectProcessor.parse_xml(expected_xml_str), xml)


async def test_with_both_element_and_attribute():
    name = f"{str(uuid.uuid4())}"
    ref_name_1 = f"{str(uuid.uuid4())}"
    ref_name_2 = f"{str(uuid.uuid4())}"

    # Two alternative paths for identifiers and reference identifiers. One
    # using elements and one using attributes. These tha both are
    # assigned values.

    xml_str = f"""
    <Test name="{name}">
      <References>
        <Reference>
          <name>{ref_name_1}</name>
          <id></id>
        </Reference>
        <Reference name="{ref_name_2}"/>
      </References>
    </Test>
    """

    schema_type = "test_schema_type"
    object_type = "test_object_type"
    root_path = "/Test"
    ref_schema_type = "test_ref_schema_type"
    ref_object_type = "test_ref_object_type"
    ref_root_path = "/RefTest"

    def name_insertion_callback(node: Element):
        # Add Name node into a specific place in the XML.
        name_node = etree.Element("Name")
        node.insert(0, name_node)
        return name_node

    def id_insertion_callback(node: Element):
        # Add ID node into a specific place in the XML.
        name_node = node.find("Name")
        if name_node is None:
            name_node = name_insertion_callback(node)
        id_node = etree.Element("ID")
        node.insert(list(node).index(name_node) + 1, id_node)
        return id_node

    def ref_name_insertion_callback(node: Element):
        # Add name node into a specific place in the XML.
        name_node = etree.Element("name")
        node.insert(0, name_node)
        return name_node

    def ref_id_insertion_callback(node: Element):
        # Add ID node into a specific place in the XML.
        name_node = node.find("name")
        if name_node is None:
            name_node = ref_name_insertion_callback(node)
        id_node = etree.Element("id")
        node.insert(list(node).index(name_node) + 1, id_node)
        return id_node

    config = XmlObjectConfig(
        schema_paths=[XmlSchemaPath(schema_type=schema_type, root_paths=[root_path])],
        object_paths=[
            XmlObjectPaths(
                schema_type=schema_type,
                object_type=object_type,
                root_path=root_path,
                identifier_paths=[
                    XmlIdentifierPath(
                        name_path="Name",
                        id_path="ID",
                        name_insertion_callback=name_insertion_callback,
                        id_insertion_callback=id_insertion_callback,
                    ),
                    XmlIdentifierPath(name_path="@name", id_path="@id"),
                ],
            )
        ],
        reference_paths=[
            XmlReferencePaths(
                schema_type=schema_type,
                ref_schema_type=ref_schema_type,
                object_type=object_type,
                ref_object_type=ref_object_type,
                root_path="/Test/References/Reference",
                ref_root_path=ref_root_path,
                paths=[
                    XmlIdentifierPath(
                        id_path="id",
                        name_path="name",
                        name_insertion_callback=ref_name_insertion_callback,
                        id_insertion_callback=ref_id_insertion_callback,
                    ),
                    XmlIdentifierPath(name_path="@name", id_path="@id"),
                ],
            )
        ],
    )

    xml = XmlObjectProcessor.parse_xml(xml_str)
    processor = XmlObjectProcessor(config, xml)

    # Get schema type
    assert processor.schema_type == schema_type

    # Get name and id
    assert processor.get_xml_object_identifier().name == name
    assert processor.get_xml_object_identifier().id is None

    # Set id
    id = f"{str(uuid.uuid4())}"
    processor.set_xml_object_id(id)
    assert processor.get_xml_object_identifier().name == name
    assert processor.get_xml_object_identifier().id == id

    # Get references
    refs = processor.get_object_references()
    assert len(refs) == 2
    assert refs[0].name == ref_name_1
    assert refs[0].id is None
    assert refs[0].schema_type == ref_schema_type
    assert refs[0].object_type == ref_object_type
    assert refs[1].name == ref_name_2
    assert refs[1].id is None
    assert refs[1].schema_type == ref_schema_type
    assert refs[1].object_type == ref_object_type

    # Set reference ids
    ref_id_1 = f"{str(uuid.uuid4())}"
    ref_id_2 = f"{str(uuid.uuid4())}"
    ref_1 = ObjectIdentifier(
        schema_type=ref_schema_type, object_type=ref_object_type, root_path=ref_root_path, name=ref_name_1, id=ref_id_1
    )
    ref_2 = ObjectIdentifier(
        schema_type=ref_schema_type, object_type=ref_object_type, root_path=ref_root_path, name=ref_name_2, id=ref_id_2
    )
    updated_refs = [ref_1, ref_2]
    processor.set_object_reference_ids(updated_refs)
    refs = processor.get_object_references()

    assert len(refs) == 2
    assert ref_1 in refs
    assert ref_2 in refs

    # Check reference ids
    assert processor.is_object_reference_ids()

    # Check XML

    expected_xml_str = f"""
        <Test name="{name}" id="{id}">
          <Name>{name}</Name>
          <ID>{id}</ID>
          <References>
            <Reference name="{ref_name_1}" id="{ref_id_1}">
              <name>{ref_name_1}</name>
              <id>{ref_id_1}</id>
           </Reference>
            <Reference name="{ref_name_2}" id="{ref_id_2}">
              <name>{ref_name_2}</name>
              <id>{ref_id_2}</id>
            </Reference>
          </References>
        </Test>
        """

    assert_xml(XmlObjectProcessor.parse_xml(expected_xml_str), xml)


async def test_mandatory_and_single():
    name_1 = f"{str(uuid.uuid4())}"
    name_2 = f"{str(uuid.uuid4())}"

    xml_str = f"""
    <Tests>
        <Test>
          <Name>{name_1}</Name>
          <ID></ID>
        </Test>
        <Test>
          <Name>{name_2}</Name>
          <ID></ID>
        </Test>
    </Tests>
    """

    schema_type = "test_schema_type"
    object_type = "test_object_type"
    set_path = "/Tests"
    root_path = "/Test"
    title_path = "/Title"
    description_path = "/Description"

    def _get_config(is_mandatory: bool, is_single: bool) -> XmlObjectConfig:
        return XmlObjectConfig(
            schema_paths=[XmlSchemaPath(schema_type=schema_type, set_path=set_path, root_paths=[root_path])],
            object_paths=[
                XmlObjectPaths(
                    schema_type=schema_type,
                    object_type=object_type,
                    root_path=root_path,
                    is_mandatory=is_mandatory,
                    is_single=is_single,
                    identifier_paths=[XmlIdentifierPath(name_path="Name", id_path="ID")],
                    title_path=title_path,
                    description_path=description_path,
                ),
            ],
            reference_paths=[],
        )

    xml = XmlDocumentsProcessor.parse_xml(xml_str)

    XmlDocumentsProcessor(_get_config(False, False), xml)
    XmlDocumentsProcessor(_get_config(True, False), xml)

    with pytest.raises(ValueError, match=f"Expecting exactly one '{schema_type}' metadata object but found 2."):
        XmlDocumentsProcessor(_get_config(True, True), xml)

    with pytest.raises(ValueError, match=f"Expecting at most one '{schema_type}' metadata object but found 2."):
        XmlDocumentsProcessor(_get_config(False, True), xml)

    with pytest.raises(ValueError, match=f"Expecting at least one '{schema_type}' metadata object but found 0."):
        XmlDocumentsProcessor(_get_config(True, False), XmlDocumentProcessor.parse_xml("<Tests></Tests>"))


def assert_object(
    processor: XmlDocumentsProcessor,
    schema_type_and_root_path: tuple[str, str],
    name: str,
    id: str | None,
    *,
    title: str | None = None,
    description: str | None = None,
) -> None:
    schema_type = schema_type_and_root_path[0]
    root_path = schema_type_and_root_path[1]
    assert processor.get_xml_object_identifier(schema_type, root_path, name).name == name
    assert processor.get_xml_object_identifier(schema_type, root_path, name).id == id
    if title:
        assert processor.get_object_processor(schema_type, root_path, name).get_object_title() == title
    if description:
        assert processor.get_object_processor(schema_type, root_path, name).get_object_description() == description


def assert_ref_length(
    processor: XmlDocumentsProcessor, schema_type_and_root_path: tuple[str, str], name: str, length: int
) -> None:
    refs = XmlDocumentProcessor.get_xml_object_processor(
        processor.xml_processor, schema_type_and_root_path[0], schema_type_and_root_path[1], name
    ).get_object_references()
    assert len(refs) == length


def assert_ref(
    processor: XmlDocumentsProcessor,
    schema_type_and_root_path: tuple[str, str],
    name: str,
    ref_schema_type_and_root_path: tuple[str, str],
    ref_name: str,
    ref_id: str | None,
) -> None:
    schema_type = schema_type_and_root_path[0]
    root_path = schema_type_and_root_path[1]
    ref_schema_type = ref_schema_type_and_root_path[0]
    ref_root_path = ref_schema_type_and_root_path[1]
    refs = XmlDocumentProcessor.get_xml_object_processor(
        processor.xml_processor, schema_type, root_path, name
    ).get_object_references()
    for ref in refs:
        if (
            ref.schema_type == ref_schema_type
            and ref.root_path == ref_root_path
            and ref.name == ref_name
            and ref.id == ref_id
        ):
            return
    assert False
