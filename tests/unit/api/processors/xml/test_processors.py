import uuid
from pathlib import Path

import pytest
from lxml import etree
from lxml.etree import _Element as Element  # noqa

from metadata_backend.api.processors.xml.configs import (
    BP_ANNOTATION_PATH,
    BP_ANNOTATION_SCHEMA,
    BP_ANNOTATION_SCHEMA_AND_PATH,
    BP_ANNOTATION_SET_PATH,
    BP_DATASET_PATH,
    BP_DATASET_SCHEMA,
    BP_DATASET_SCHEMA_AND_PATH,
    BP_FULL_SUBMISSION_XML_OBJECT_CONFIG,
    BP_IMAGE_PATH,
    BP_IMAGE_SCHEMA,
    BP_IMAGE_SCHEMA_AND_PATH,
    BP_LANDING_PAGE_PATH,
    BP_LANDING_PAGE_SCHEMA,
    BP_LANDING_PAGE_SCHEMA_AND_PATH,
    BP_OBSERVATION_PATH,
    BP_OBSERVATION_SCHEMA,
    BP_OBSERVATION_SCHEMA_AND_PATH,
    BP_OBSERVER_PATH,
    BP_OBSERVER_SCHEMA,
    BP_OBSERVER_SCHEMA_AND_PATH,
    BP_ORGANISATION_PATH,
    BP_ORGANISATION_SCHEMA,
    BP_ORGANISATION_SCHEMA_AND_PATH,
    BP_POLICY_PATH,
    BP_POLICY_SCHEMA,
    BP_POLICY_SCHEMA_AND_PATH,
    BP_REMS_PATH,
    BP_REMS_SCHEMA,
    BP_REMS_SCHEMA_AND_PATH,
    BP_SAMPLE_BIOLOGICAL_BEING_PATH,
    BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH,
    BP_SAMPLE_BLOCK_PATH,
    BP_SAMPLE_BLOCK_SCHEMA_AND_PATH,
    BP_SAMPLE_CASE_PATH,
    BP_SAMPLE_CASE_SCHEMA_AND_PATH,
    BP_SAMPLE_SCHEMA,
    BP_SAMPLE_SET_PATH,
    BP_SAMPLE_SLIDE_PATH,
    BP_SAMPLE_SLIDE_SCHEMA_AND_PATH,
    BP_SAMPLE_SPECIMEN_PATH,
    BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH,
    BP_STAINING_PATH,
    BP_STAINING_SCHEMA,
    BP_STAINING_SCHEMA_AND_PATH,
    FEGA_ANALYSIS_PATH,
    FEGA_ANALYSIS_SCHEMA,
    FEGA_ANALYSIS_SCHEMA_AND_PATH,
    FEGA_DAC_PATH,
    FEGA_DAC_SCHEMA,
    FEGA_DAC_SCHEMA_AND_PATH,
    FEGA_DATASET_PATH,
    FEGA_DATASET_SCHEMA,
    FEGA_DATASET_SCHEMA_AND_PATH,
    FEGA_EXPERIMENT_PATH,
    FEGA_EXPERIMENT_SCHEMA,
    FEGA_EXPERIMENT_SCHEMA_AND_PATH,
    FEGA_FULL_SUBMISSION_XML_OBJECT_CONFIG,
    FEGA_POLICY_PATH,
    FEGA_POLICY_SCHEMA,
    FEGA_POLICY_SCHEMA_AND_PATH,
    FEGA_RUN_PATH,
    FEGA_RUN_SCHEMA,
    FEGA_RUN_SCHEMA_AND_PATH,
    FEGA_SAMPLE_PATH,
    FEGA_SAMPLE_SCHEMA,
    FEGA_SAMPLE_SCHEMA_AND_PATH,
    FEGA_STUDY_PATH,
    FEGA_STUDY_SCHEMA,
    FEGA_STUDY_SCHEMA_AND_PATH,
    FEGA_SUBMISSION_PATH,
    FEGA_SUBMISSION_SCHEMA,
    FEGA_SUBMISSION_SCHEMA_AND_PATH,
    _get_xml_object_type_bp,
    _get_xml_object_type_fega,
)
from metadata_backend.api.processors.xml.models import (
    XmlIdentifierPath,
    XmlObjectConfig,
    XmlObjectIdentifier,
    XmlObjectPaths,
    XmlReferencePaths,
    XmlSchemaPath,
)
from metadata_backend.api.processors.xml.processors import (
    XmlDocumentProcessor,
    XmlDocumentsProcessor,
    XmlFileDocumentsProcessor,
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
    assert processor.get_xml_object_title() == title
    assert processor.get_xml_object_description() == description

    # Set id
    id = f"{str(uuid.uuid4())}"
    processor.set_xml_object_id(id)
    assert processor.get_xml_object_identifier().name == name
    assert processor.get_xml_object_identifier().id == id

    # Get references
    refs = processor.get_xml_object_references()
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
    ref_1 = XmlObjectIdentifier(
        schema_type=ref_schema_type, object_type=ref_object_type, root_path=ref_root_path, name=ref_name_1, id=ref_id_1
    )
    ref_2 = XmlObjectIdentifier(
        schema_type=ref_schema_type, object_type=ref_object_type, root_path=ref_root_path, name=ref_name_2, id=ref_id_2
    )
    updated_refs = [ref_1, ref_2]
    processor.set_xml_object_reference_ids(updated_refs)
    refs = processor.get_xml_object_references()

    assert len(refs) == 2
    assert ref_1 in refs
    assert ref_2 in refs

    # Check reference ids
    assert processor.is_xml_object_reference_ids() == True

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
    refs = processor.get_xml_object_references()
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
    ref_1 = XmlObjectIdentifier(
        schema_type=ref_schema_type, object_type=ref_object_type, root_path=ref_root_path, name=ref_name_1, id=ref_id_1
    )
    ref_2 = XmlObjectIdentifier(
        schema_type=ref_schema_type, object_type=ref_object_type, root_path=ref_root_path, name=ref_name_2, id=ref_id_2
    )
    updated_refs = [ref_1, ref_2]
    processor.set_xml_object_reference_ids(updated_refs)
    refs = processor.get_xml_object_references()

    assert len(refs) == 2
    assert ref_1 in refs
    assert ref_2 in refs

    # Check reference ids
    assert processor.is_xml_object_reference_ids() == True

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
    assert processor.get_xml_object_title() == title
    assert processor.get_xml_object_description() == description

    # Set id
    id = f"{str(uuid.uuid4())}"
    processor.set_xml_object_id(id)
    assert processor.get_xml_object_identifier().name == name
    assert processor.get_xml_object_identifier().id == id

    # Get references
    refs = processor.get_xml_object_references()
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
    ref_1 = XmlObjectIdentifier(
        schema_type=ref_schema_type, object_type=ref_object_type, root_path=ref_root_path, name=ref_name_1, id=ref_id_1
    )
    ref_2 = XmlObjectIdentifier(
        schema_type=ref_schema_type, object_type=ref_object_type, root_path=ref_root_path, name=ref_name_2, id=ref_id_2
    )
    updated_refs = [ref_1, ref_2]
    processor.set_xml_object_reference_ids(updated_refs)
    refs = processor.get_xml_object_references()

    assert len(refs) == 2
    assert ref_1 in refs
    assert ref_2 in refs

    # Check reference ids
    assert processor.is_xml_object_reference_ids() == True

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
    refs = processor.get_xml_object_references()
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
    ref_1 = XmlObjectIdentifier(
        schema_type=ref_schema_type, object_type=ref_object_type, root_path=ref_root_path, name=ref_name_1, id=ref_id_1
    )
    ref_2 = XmlObjectIdentifier(
        schema_type=ref_schema_type, object_type=ref_object_type, root_path=ref_root_path, name=ref_name_2, id=ref_id_2
    )
    updated_refs = [ref_1, ref_2]
    processor.set_xml_object_reference_ids(updated_refs)
    refs = processor.get_xml_object_references()

    assert len(refs) == 2
    assert ref_1 in refs
    assert ref_2 in refs

    # Check reference ids
    assert processor.is_xml_object_reference_ids() == True

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
        assert processor.get_xml_object_processor(schema_type, root_path, name).get_xml_object_title() == title
    if description:
        assert (
            processor.get_xml_object_processor(schema_type, root_path, name).get_xml_object_description() == description
        )


def assert_ref_length(
    processor: XmlDocumentsProcessor, schema_type_and_root_path: tuple[str, str], name: str, length: int
) -> None:
    refs = XmlDocumentProcessor.get_xml_object_processor(
        processor.xml_processor, schema_type_and_root_path[0], schema_type_and_root_path[1], name
    ).get_xml_object_references()
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
    ).get_xml_object_references()
    for ref in refs:
        if (
            ref.schema_type == ref_schema_type
            and ref.root_path == ref_root_path
            and ref.name == ref_name
            and ref.id == ref_id
        ):
            return
    assert False


def create_xml_object_identifier_bp(schema_type: str, root_path: str, name: str, id: str):
    return XmlObjectIdentifier(
        schema_type=schema_type, object_type=_get_xml_object_type_bp(root_path), root_path=root_path, name=name, id=id
    )


def create_xml_object_identifier_fega(schema_type: str, root_path: str, name: str, id: str):
    return XmlObjectIdentifier(
        schema_type=schema_type, object_type=_get_xml_object_type_fega(root_path), root_path=root_path, name=name, id=id
    )


async def test_bp_submission_1():
    """Test self-contained BP submission with alias references."""

    submission_dir = TEST_FILES_DIR / "xml" / "bp" / "submission_1"

    processor = XmlFileDocumentsProcessor(
        BP_FULL_SUBMISSION_XML_OBJECT_CONFIG,
        str(submission_dir),
        [
            "dataset.xml",
            "policy.xml",
            "image.xml",
            "annotation.xml",
            "observation.xml",
            "observer.xml",
            "sample.xml",
            "staining.xml",
            "landing_page.xml",
            "rems.xml",
            "organisation.xml",
            # "datacite.xml": [], # TODO(improve): implement DataCite XML
        ],
    )

    annotation_name = "1"
    dataset_name = "1"
    image_name = "1"
    observation_name = "1"
    observer_name = "1"
    policy_name = "1"
    sample_biological_being_name = "1"
    sample_case_name = "1"
    sample_specimen_name = "1"
    sample_block_name = "1"
    sample_slide_name = "1"
    staining_name = "1"
    landing_page_name = "1"
    organisation_name = "1"
    rems_name = "1"

    # Test configuration with annotation and sample
    config = BP_FULL_SUBMISSION_XML_OBJECT_CONFIG
    annotation_object_type = _get_xml_object_type_bp(BP_ANNOTATION_PATH)
    assert config.get_root_path(annotation_object_type) == BP_ANNOTATION_PATH
    assert config.get_set_path(object_type=annotation_object_type) == BP_ANNOTATION_SET_PATH
    assert config.get_set_path(schema_type=BP_ANNOTATION_SCHEMA) == BP_ANNOTATION_SET_PATH
    assert config.get_object_type(BP_ANNOTATION_PATH) == annotation_object_type
    assert config.get_schema_type(annotation_object_type) == BP_ANNOTATION_SCHEMA
    assert config.get_object_types(BP_ANNOTATION_SCHEMA) == [annotation_object_type]

    sample_object_type = _get_xml_object_type_bp(BP_SAMPLE_CASE_PATH)
    assert config.get_root_path(sample_object_type) == BP_SAMPLE_CASE_PATH
    assert config.get_set_path(object_type=sample_object_type) == BP_SAMPLE_SET_PATH
    assert config.get_set_path(schema_type=BP_SAMPLE_SCHEMA) == BP_SAMPLE_SET_PATH
    assert config.get_object_type(BP_SAMPLE_CASE_PATH) == sample_object_type
    assert config.get_schema_type(sample_object_type) == BP_SAMPLE_SCHEMA
    assert sample_object_type in config.get_object_types(BP_SAMPLE_SCHEMA)
    assert len(config.get_object_types(BP_SAMPLE_SCHEMA)) == 5

    # Assert not accessioned state
    #

    # Annotation
    assert_object(processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, None)
    assert_ref_length(processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, 1)
    assert_ref(processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, BP_IMAGE_SCHEMA_AND_PATH, image_name, None)
    # Dataset
    assert_object(
        processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, None, title="test_title", description="test_description"
    )
    assert_ref_length(processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, 3)
    assert_ref(processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, BP_IMAGE_SCHEMA_AND_PATH, image_name, None)
    assert_ref(
        processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, None
    )
    assert_ref(
        processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, BP_OBSERVATION_SCHEMA_AND_PATH, observation_name, None
    )
    # Image
    assert_object(processor, BP_IMAGE_SCHEMA_AND_PATH, image_name, None)
    assert_ref_length(processor, BP_IMAGE_SCHEMA_AND_PATH, image_name, 1)
    assert_ref(
        processor, BP_IMAGE_SCHEMA_AND_PATH, image_name, BP_SAMPLE_SLIDE_SCHEMA_AND_PATH, sample_slide_name, None
    )
    # Observation
    assert_object(processor, BP_OBSERVATION_SCHEMA_AND_PATH, observation_name, None)
    assert_ref_length(processor, BP_OBSERVATION_SCHEMA_AND_PATH, observation_name, 2)
    assert_ref(
        processor,
        BP_OBSERVATION_SCHEMA_AND_PATH,
        observation_name,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        annotation_name,
        None,
    )
    assert_ref(
        processor, BP_OBSERVATION_SCHEMA_AND_PATH, observation_name, BP_OBSERVER_SCHEMA_AND_PATH, observer_name, None
    )
    # Observer
    assert_object(processor, BP_OBSERVER_SCHEMA_AND_PATH, observer_name, None)
    assert_ref_length(processor, BP_OBSERVER_SCHEMA_AND_PATH, observer_name, 0)
    # Policy
    assert_object(processor, BP_POLICY_SCHEMA_AND_PATH, policy_name, None)
    assert_ref_length(processor, BP_POLICY_SCHEMA_AND_PATH, policy_name, 1)
    assert_ref(processor, BP_POLICY_SCHEMA_AND_PATH, policy_name, BP_DATASET_SCHEMA_AND_PATH, dataset_name, None)
    # Sample
    assert_object(processor, BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH, sample_biological_being_name, None)
    assert_object(processor, BP_SAMPLE_CASE_SCHEMA_AND_PATH, sample_case_name, None)
    assert_object(processor, BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH, sample_specimen_name, None)
    assert_object(processor, BP_SAMPLE_BLOCK_SCHEMA_AND_PATH, sample_block_name, None)
    assert_object(processor, BP_SAMPLE_SLIDE_SCHEMA_AND_PATH, sample_slide_name, None)
    assert_ref_length(processor, BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH, sample_biological_being_name, 0)
    assert_ref_length(processor, BP_SAMPLE_CASE_SCHEMA_AND_PATH, sample_case_name, 1)
    assert_ref(
        processor,
        BP_SAMPLE_CASE_SCHEMA_AND_PATH,
        sample_case_name,
        BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH,
        sample_biological_being_name,
        None,
    )
    assert_ref_length(processor, BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH, sample_specimen_name, 2)
    assert_ref(
        processor,
        BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH,
        sample_specimen_name,
        BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH,
        sample_biological_being_name,
        None,
    )
    assert_ref(
        processor,
        BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH,
        sample_specimen_name,
        BP_SAMPLE_CASE_SCHEMA_AND_PATH,
        sample_case_name,
        None,
    )
    assert_ref_length(processor, BP_SAMPLE_BLOCK_SCHEMA_AND_PATH, sample_block_name, 1)
    assert_ref(
        processor,
        BP_SAMPLE_BLOCK_SCHEMA_AND_PATH,
        sample_block_name,
        BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH,
        sample_specimen_name,
        None,
    )
    assert_ref_length(processor, BP_SAMPLE_SLIDE_SCHEMA_AND_PATH, sample_slide_name, 2)
    assert_ref(
        processor,
        BP_SAMPLE_SLIDE_SCHEMA_AND_PATH,
        sample_slide_name,
        BP_SAMPLE_BLOCK_SCHEMA_AND_PATH,
        sample_block_name,
        None,
    )
    assert_ref(
        processor, BP_SAMPLE_SLIDE_SCHEMA_AND_PATH, sample_slide_name, BP_STAINING_SCHEMA_AND_PATH, staining_name, None
    )
    # Staining
    assert_object(processor, BP_STAINING_SCHEMA_AND_PATH, staining_name, None)
    assert_ref_length(processor, BP_STAINING_SCHEMA_AND_PATH, staining_name, 0)
    # Landing page
    assert_object(processor, BP_LANDING_PAGE_SCHEMA_AND_PATH, landing_page_name, None)
    assert_ref_length(processor, BP_LANDING_PAGE_SCHEMA_AND_PATH, landing_page_name, 1)
    assert_ref(
        processor, BP_LANDING_PAGE_SCHEMA_AND_PATH, landing_page_name, BP_DATASET_SCHEMA_AND_PATH, dataset_name, None
    )
    # Organisation
    assert_object(processor, BP_ORGANISATION_SCHEMA_AND_PATH, organisation_name, None, title="test_name")
    assert_ref_length(processor, BP_ORGANISATION_SCHEMA_AND_PATH, organisation_name, 1)
    assert_ref(
        processor, BP_ORGANISATION_SCHEMA_AND_PATH, organisation_name, BP_DATASET_SCHEMA_AND_PATH, dataset_name, None
    )
    # Rems
    assert_object(processor, BP_REMS_SCHEMA_AND_PATH, rems_name, None)
    assert_ref_length(processor, BP_REMS_SCHEMA_AND_PATH, rems_name, 1)
    assert_ref(processor, BP_REMS_SCHEMA_AND_PATH, rems_name, BP_DATASET_SCHEMA_AND_PATH, dataset_name, None)

    # Assign accessions
    #

    # Annotation
    annotation_id = f"annotation_{str(uuid.uuid4())}"
    processor.set_xml_object_id(
        create_xml_object_identifier_bp(BP_ANNOTATION_SCHEMA, BP_ANNOTATION_PATH, annotation_name, annotation_id)
    )
    # Dataset
    dataset_id = f"dataset_{str(uuid.uuid4())}"
    processor.set_xml_object_id(
        create_xml_object_identifier_bp(BP_DATASET_SCHEMA, BP_DATASET_PATH, dataset_name, dataset_id)
    )
    # Image
    image_id = f"image_{str(uuid.uuid4())}"
    processor.set_xml_object_id(create_xml_object_identifier_bp(BP_IMAGE_SCHEMA, BP_IMAGE_PATH, image_name, image_id))
    # Observation
    observation_id = f"observation_{str(uuid.uuid4())}"
    processor.set_xml_object_id(
        create_xml_object_identifier_bp(BP_OBSERVATION_SCHEMA, BP_OBSERVATION_PATH, observation_name, observation_id)
    )
    # Observer
    observer_id = f"observer_{str(uuid.uuid4())}"
    processor.set_xml_object_id(
        create_xml_object_identifier_bp(BP_OBSERVER_SCHEMA, BP_OBSERVER_PATH, observer_name, observer_id)
    )
    # Policy
    policy_id = f"policy_{str(uuid.uuid4())}"
    processor.set_xml_object_id(
        create_xml_object_identifier_bp(BP_POLICY_SCHEMA, BP_POLICY_PATH, policy_name, policy_id)
    )
    # Staining
    staining_id = f"staining_{str(uuid.uuid4())}"
    processor.set_xml_object_id(
        create_xml_object_identifier_bp(BP_STAINING_SCHEMA, BP_STAINING_PATH, staining_name, staining_id)
    )
    # Landing page
    landing_page_id = f"landing_page_{str(uuid.uuid4())}"
    processor.set_xml_object_id(
        create_xml_object_identifier_bp(
            BP_LANDING_PAGE_SCHEMA, BP_LANDING_PAGE_PATH, landing_page_name, landing_page_id
        )
    )
    # Sample
    sample_biological_being_id = f"sample_biological_being_{str(uuid.uuid4())}"
    sample_case_id = f"sample_case_{str(uuid.uuid4())}"
    sample_specimen_id = f"sample_specimen_{str(uuid.uuid4())}"
    sample_block_id = f"sample_block_{str(uuid.uuid4())}"
    sample_slide_id = f"sample_slide_{str(uuid.uuid4())}"
    processor.set_xml_object_id(
        create_xml_object_identifier_bp(
            BP_SAMPLE_SCHEMA, BP_SAMPLE_BIOLOGICAL_BEING_PATH, sample_biological_being_name, sample_biological_being_id
        )
    )
    processor.set_xml_object_id(
        create_xml_object_identifier_bp(BP_SAMPLE_SCHEMA, BP_SAMPLE_CASE_PATH, sample_case_name, sample_case_id)
    )
    processor.set_xml_object_id(
        create_xml_object_identifier_bp(
            BP_SAMPLE_SCHEMA, BP_SAMPLE_SPECIMEN_PATH, sample_specimen_name, sample_specimen_id
        )
    )
    processor.set_xml_object_id(
        create_xml_object_identifier_bp(BP_SAMPLE_SCHEMA, BP_SAMPLE_BLOCK_PATH, sample_block_name, sample_block_id)
    )
    processor.set_xml_object_id(
        create_xml_object_identifier_bp(BP_SAMPLE_SCHEMA, BP_SAMPLE_SLIDE_PATH, sample_slide_name, sample_slide_id)
    )
    # Organisation
    organisation_id = f"organisation_{str(uuid.uuid4())}"
    processor.set_xml_object_id(
        create_xml_object_identifier_bp(
            BP_ORGANISATION_SCHEMA, BP_ORGANISATION_PATH, organisation_name, organisation_id
        )
    )
    # Rems
    rems_id = f"rems_{str(uuid.uuid4())}"
    processor.set_xml_object_id(create_xml_object_identifier_bp(BP_REMS_SCHEMA, BP_REMS_PATH, rems_name, rems_id))

    # Assert accessioned state
    #

    # Annotation
    assert_object(processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, annotation_id)
    assert_ref_length(processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, 1)
    assert_ref(
        processor, BP_ANNOTATION_SCHEMA_AND_PATH, annotation_name, BP_IMAGE_SCHEMA_AND_PATH, image_name, image_id
    )
    # Dataset
    assert_object(processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, dataset_id)
    assert_ref_length(processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, 3)
    assert_ref(processor, BP_DATASET_SCHEMA_AND_PATH, dataset_name, BP_IMAGE_SCHEMA_AND_PATH, image_name, image_id)
    assert_ref(
        processor,
        BP_DATASET_SCHEMA_AND_PATH,
        dataset_name,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        annotation_name,
        annotation_id,
    )
    assert_ref(
        processor,
        BP_DATASET_SCHEMA_AND_PATH,
        dataset_name,
        BP_OBSERVATION_SCHEMA_AND_PATH,
        observation_name,
        observation_id,
    )
    # Image
    assert_object(processor, BP_IMAGE_SCHEMA_AND_PATH, image_name, image_id)
    assert_ref_length(processor, BP_IMAGE_SCHEMA_AND_PATH, image_name, 1)
    assert_ref(
        processor,
        BP_IMAGE_SCHEMA_AND_PATH,
        image_name,
        BP_SAMPLE_SLIDE_SCHEMA_AND_PATH,
        sample_slide_name,
        sample_slide_id,
    )
    # Observation
    assert_object(processor, BP_OBSERVATION_SCHEMA_AND_PATH, observation_name, observation_id)
    assert_ref_length(processor, BP_OBSERVATION_SCHEMA_AND_PATH, observation_name, 2)
    assert_ref(
        processor,
        BP_OBSERVATION_SCHEMA_AND_PATH,
        observation_name,
        BP_ANNOTATION_SCHEMA_AND_PATH,
        annotation_name,
        annotation_id,
    )
    assert_ref(
        processor,
        BP_OBSERVATION_SCHEMA_AND_PATH,
        observation_name,
        BP_OBSERVER_SCHEMA_AND_PATH,
        observer_name,
        observer_id,
    )
    # Observer
    assert_object(processor, BP_OBSERVER_SCHEMA_AND_PATH, observer_name, observer_id)
    assert_ref_length(processor, BP_OBSERVER_SCHEMA_AND_PATH, observer_name, 0)
    # Policy
    assert_object(processor, BP_POLICY_SCHEMA_AND_PATH, policy_name, policy_id)
    assert_ref_length(processor, BP_POLICY_SCHEMA_AND_PATH, policy_name, 1)
    assert_ref(processor, BP_POLICY_SCHEMA_AND_PATH, policy_name, BP_DATASET_SCHEMA_AND_PATH, dataset_name, dataset_id)
    # Sample
    assert_object(
        processor, BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH, sample_biological_being_name, sample_biological_being_id
    )
    assert_object(processor, BP_SAMPLE_CASE_SCHEMA_AND_PATH, sample_case_name, sample_case_id)
    assert_object(processor, BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH, sample_specimen_name, sample_specimen_id)
    assert_object(processor, BP_SAMPLE_BLOCK_SCHEMA_AND_PATH, sample_block_name, sample_block_id)
    assert_object(processor, BP_SAMPLE_SLIDE_SCHEMA_AND_PATH, sample_slide_name, sample_slide_id)
    assert_ref_length(processor, BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH, sample_biological_being_name, 0)
    assert_ref_length(processor, BP_SAMPLE_CASE_SCHEMA_AND_PATH, sample_case_name, 1)
    assert_ref(
        processor,
        BP_SAMPLE_CASE_SCHEMA_AND_PATH,
        sample_case_name,
        BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH,
        sample_biological_being_name,
        sample_biological_being_id,
    )
    assert_ref_length(processor, BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH, sample_specimen_name, 2)
    assert_ref(
        processor,
        BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH,
        sample_specimen_name,
        BP_SAMPLE_BIOLOGICAL_BEING_SCHEMA_AND_PATH,
        sample_biological_being_name,
        sample_biological_being_id,
    )
    assert_ref(
        processor,
        BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH,
        sample_specimen_name,
        BP_SAMPLE_CASE_SCHEMA_AND_PATH,
        sample_case_name,
        sample_case_id,
    )
    assert_ref_length(processor, BP_SAMPLE_BLOCK_SCHEMA_AND_PATH, sample_block_name, 1)
    assert_ref(
        processor,
        BP_SAMPLE_BLOCK_SCHEMA_AND_PATH,
        sample_block_name,
        BP_SAMPLE_SPECIMEN_SCHEMA_AND_PATH,
        sample_specimen_name,
        sample_specimen_id,
    )
    assert_ref_length(processor, BP_SAMPLE_SLIDE_SCHEMA_AND_PATH, sample_slide_name, 2)
    assert_ref(
        processor,
        BP_SAMPLE_SLIDE_SCHEMA_AND_PATH,
        sample_slide_name,
        BP_SAMPLE_BLOCK_SCHEMA_AND_PATH,
        sample_block_name,
        sample_block_id,
    )
    assert_ref(
        processor,
        BP_SAMPLE_SLIDE_SCHEMA_AND_PATH,
        sample_slide_name,
        BP_STAINING_SCHEMA_AND_PATH,
        staining_name,
        staining_id,
    )
    # Staining
    assert_object(processor, BP_STAINING_SCHEMA_AND_PATH, staining_name, staining_id)
    assert_ref_length(processor, BP_STAINING_SCHEMA_AND_PATH, staining_name, 0)
    # Landing page
    assert_object(processor, BP_LANDING_PAGE_SCHEMA_AND_PATH, landing_page_name, landing_page_id)
    assert_ref_length(processor, BP_LANDING_PAGE_SCHEMA_AND_PATH, landing_page_name, 1)
    assert_ref(
        processor,
        BP_LANDING_PAGE_SCHEMA_AND_PATH,
        landing_page_name,
        BP_DATASET_SCHEMA_AND_PATH,
        dataset_name,
        dataset_id,
    )
    # Organisation
    assert_object(processor, BP_ORGANISATION_SCHEMA_AND_PATH, organisation_name, organisation_id)
    assert_ref_length(processor, BP_ORGANISATION_SCHEMA_AND_PATH, organisation_name, 1)
    assert_ref(
        processor,
        BP_ORGANISATION_SCHEMA_AND_PATH,
        organisation_name,
        BP_DATASET_SCHEMA_AND_PATH,
        dataset_name,
        dataset_id,
    )
    # Rems
    assert_object(processor, BP_REMS_SCHEMA_AND_PATH, rems_name, rems_id)
    assert_ref_length(processor, BP_REMS_SCHEMA_AND_PATH, rems_name, 1)
    assert_ref(processor, BP_REMS_SCHEMA_AND_PATH, rems_name, BP_DATASET_SCHEMA_AND_PATH, dataset_name, dataset_id)


async def test_fega_submission_1():
    """Test self-contained FEGA submission with alias references."""

    submission_dir = TEST_FILES_DIR / "xml" / "fega" / "submission_1"

    processor = XmlFileDocumentsProcessor(
        FEGA_FULL_SUBMISSION_XML_OBJECT_CONFIG,
        str(submission_dir),
        [
            "analysis.xml",
            "dac.xml",
            "dataset.xml",
            "experiment.xml",
            "policy.xml",
            "run.xml",
            "sample.xml",
            "study.xml",
            "submission.xml",
        ],
    )

    analysis_name = "1"
    dac_name = "1"
    dataset_name = "1"
    experiment_name = "1"
    policy_name = "1"
    run_name = "1"
    sample_name = "1"
    study_name = "1"
    submission_name = "1"

    # Assert not accessioned state
    #

    # Analysis
    assert_object(processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, None, title="test_title")
    assert_ref_length(processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, 4)
    assert_ref(processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, FEGA_STUDY_SCHEMA_AND_PATH, study_name, None)
    assert_ref(processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, FEGA_SAMPLE_SCHEMA_AND_PATH, sample_name, None)
    assert_ref(
        processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, None
    )
    assert_ref(processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, FEGA_RUN_SCHEMA_AND_PATH, run_name, None)
    # Dac
    assert_object(processor, FEGA_DAC_SCHEMA_AND_PATH, dac_name, None, title="test_title")
    assert_ref_length(processor, FEGA_DAC_SCHEMA_AND_PATH, dac_name, 0)
    # Dataset
    assert_object(
        processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, None, title="test_title", description="test_description"
    )
    assert_ref_length(processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, 3)
    assert_ref(processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, FEGA_RUN_SCHEMA_AND_PATH, run_name, None)
    assert_ref(
        processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, None
    )
    assert_ref(processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, FEGA_POLICY_SCHEMA_AND_PATH, policy_name, None)
    # Experiment
    assert_object(processor, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, None, title="test_title")
    assert_ref_length(processor, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, 2)
    assert_ref(
        processor, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, FEGA_STUDY_SCHEMA_AND_PATH, study_name, None
    )
    assert_ref(
        processor, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, FEGA_SAMPLE_SCHEMA_AND_PATH, sample_name, None
    )
    # Policy
    assert_object(processor, FEGA_POLICY_SCHEMA_AND_PATH, policy_name, None, title="test_title")
    assert_ref_length(processor, FEGA_POLICY_SCHEMA_AND_PATH, policy_name, 1)
    assert_ref(processor, FEGA_POLICY_SCHEMA_AND_PATH, policy_name, FEGA_DAC_SCHEMA_AND_PATH, dac_name, None)
    # Run
    assert_object(processor, FEGA_RUN_SCHEMA_AND_PATH, run_name, None, title="test_title")
    assert_ref_length(processor, FEGA_RUN_SCHEMA_AND_PATH, run_name, 1)
    assert_ref(processor, FEGA_RUN_SCHEMA_AND_PATH, run_name, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, None)
    # Sample
    assert_object(
        processor, FEGA_SAMPLE_SCHEMA_AND_PATH, sample_name, None, title="test_title", description="test_description"
    )
    assert_ref_length(processor, FEGA_SAMPLE_SCHEMA_AND_PATH, sample_name, 0)
    # Study
    assert_object(
        processor, FEGA_STUDY_SCHEMA_AND_PATH, study_name, None, title="test_title", description="test_description"
    )
    assert_ref_length(processor, FEGA_STUDY_SCHEMA_AND_PATH, study_name, 0)
    # Submission
    assert_object(processor, FEGA_SUBMISSION_SCHEMA_AND_PATH, submission_name, None)
    assert_ref_length(processor, FEGA_SUBMISSION_SCHEMA_AND_PATH, submission_name, 0)

    # Assign accessions
    #

    # Analysis
    analysis_id = f"analysis_{str(uuid.uuid4())}"
    processor.set_xml_object_id(
        create_xml_object_identifier_fega(FEGA_ANALYSIS_SCHEMA, FEGA_ANALYSIS_PATH, analysis_name, analysis_id)
    )
    # Dac
    dac_id = f"dac_{str(uuid.uuid4())}"
    processor.set_xml_object_id(create_xml_object_identifier_fega(FEGA_DAC_SCHEMA, FEGA_DAC_PATH, dac_name, dac_id))
    # Dataset
    dataset_id = f"dataset_{str(uuid.uuid4())}"
    processor.set_xml_object_id(
        create_xml_object_identifier_fega(FEGA_DATASET_SCHEMA, FEGA_DATASET_PATH, dataset_name, dataset_id)
    )
    # Experiment
    experiment_id = f"experiment_{str(uuid.uuid4())}"
    processor.set_xml_object_id(
        create_xml_object_identifier_fega(FEGA_EXPERIMENT_SCHEMA, FEGA_EXPERIMENT_PATH, experiment_name, experiment_id)
    )
    # Policy
    policy_id = f"policy_{str(uuid.uuid4())}"
    processor.set_xml_object_id(
        create_xml_object_identifier_fega(FEGA_POLICY_SCHEMA, FEGA_POLICY_PATH, policy_name, policy_id)
    )
    # Run
    run_id = f"run_{str(uuid.uuid4())}"
    processor.set_xml_object_id(create_xml_object_identifier_fega(FEGA_RUN_SCHEMA, FEGA_RUN_PATH, run_name, run_id))
    # Sample
    sample_id = f"sample_{str(uuid.uuid4())}"
    processor.set_xml_object_id(
        create_xml_object_identifier_fega(FEGA_SAMPLE_SCHEMA, FEGA_SAMPLE_PATH, sample_name, sample_id)
    )
    # Study
    study_id = f"study_{str(uuid.uuid4())}"
    processor.set_xml_object_id(
        create_xml_object_identifier_fega(FEGA_STUDY_SCHEMA, FEGA_STUDY_PATH, study_name, study_id)
    )
    # Submission
    submission_id = f"submission_{str(uuid.uuid4())}"
    processor.set_xml_object_id(
        create_xml_object_identifier_fega(FEGA_SUBMISSION_SCHEMA, FEGA_SUBMISSION_PATH, submission_name, submission_id)
    )

    # Assert accessioned state
    #

    # Analysis
    assert_object(processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, analysis_id)
    assert_ref_length(processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, 4)
    assert_ref(
        processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, FEGA_STUDY_SCHEMA_AND_PATH, study_name, study_id
    )
    assert_ref(
        processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, FEGA_SAMPLE_SCHEMA_AND_PATH, sample_name, sample_id
    )
    assert_ref(
        processor,
        FEGA_ANALYSIS_SCHEMA_AND_PATH,
        analysis_name,
        FEGA_EXPERIMENT_SCHEMA_AND_PATH,
        experiment_name,
        experiment_id,
    )
    assert_ref(processor, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, FEGA_RUN_SCHEMA_AND_PATH, run_name, run_id)
    # Dac
    assert_object(processor, FEGA_DAC_SCHEMA_AND_PATH, dac_name, dac_id)
    assert_ref_length(processor, FEGA_DAC_SCHEMA_AND_PATH, dac_name, 0)
    # Dataset
    assert_object(processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, dataset_id)
    assert_ref_length(processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, 3)
    assert_ref(processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, FEGA_RUN_SCHEMA_AND_PATH, run_name, run_id)
    assert_ref(
        processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, FEGA_ANALYSIS_SCHEMA_AND_PATH, analysis_name, analysis_id
    )
    assert_ref(
        processor, FEGA_DATASET_SCHEMA_AND_PATH, dataset_name, FEGA_POLICY_SCHEMA_AND_PATH, policy_name, policy_id
    )
    # Experiment
    assert_object(processor, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, experiment_id)
    assert_ref_length(processor, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, 2)
    assert_ref(
        processor, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, FEGA_STUDY_SCHEMA_AND_PATH, study_name, study_id
    )
    assert_ref(
        processor, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, FEGA_SAMPLE_SCHEMA_AND_PATH, sample_name, sample_id
    )
    # Policy
    assert_object(processor, FEGA_POLICY_SCHEMA_AND_PATH, policy_name, policy_id)
    assert_ref_length(processor, FEGA_POLICY_SCHEMA_AND_PATH, policy_name, 1)
    assert_ref(processor, FEGA_POLICY_SCHEMA_AND_PATH, policy_name, FEGA_DAC_SCHEMA_AND_PATH, dac_name, dac_id)
    # Run
    assert_object(processor, FEGA_RUN_SCHEMA_AND_PATH, run_name, run_id)
    assert_ref_length(processor, FEGA_RUN_SCHEMA_AND_PATH, run_name, 1)
    assert_ref(
        processor, FEGA_RUN_SCHEMA_AND_PATH, run_name, FEGA_EXPERIMENT_SCHEMA_AND_PATH, experiment_name, experiment_id
    )
    # Sample
    assert_object(processor, FEGA_SAMPLE_SCHEMA_AND_PATH, sample_name, sample_id)
    assert_ref_length(processor, FEGA_SAMPLE_SCHEMA_AND_PATH, sample_name, 0)
    # Study
    assert_object(processor, FEGA_STUDY_SCHEMA_AND_PATH, study_name, study_id)
    assert_ref_length(processor, FEGA_STUDY_SCHEMA_AND_PATH, study_name, 0)
    # Submission
    assert_object(processor, FEGA_SUBMISSION_SCHEMA_AND_PATH, submission_name, submission_id)
    assert_ref_length(processor, FEGA_SUBMISSION_SCHEMA_AND_PATH, submission_name, 0)
