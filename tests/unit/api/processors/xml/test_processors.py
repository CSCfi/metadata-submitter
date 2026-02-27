import uuid

import pytest

from metadata_backend.api.processors.models import ObjectIdentifier
from metadata_backend.api.processors.xml.bigpicture import BP_IMAGE_OBJECT_TYPE, BP_IMAGE_PATH, BP_IMAGE_SCHEMA
from metadata_backend.api.services.submission.bigpicture import BigPictureObjectSubmissionService
from tests.utils import bp_objects


async def test_object_name():
    """Test object name functionality."""
    objects, _ = bp_objects(is_update=False)
    docs_processor, _ = BigPictureObjectSubmissionService._create_processor(objects)

    schema_type = BP_IMAGE_SCHEMA
    object_type = BP_IMAGE_OBJECT_TYPE
    root_path = BP_IMAGE_PATH

    # Check original image names.
    obj_processor = docs_processor.get_object_processor(schema_type=schema_type, root_path=root_path, name="1")
    assert obj_processor.get_xml_object_identifier().name == "1"
    obj_processor = docs_processor.get_object_processor(schema_type=schema_type, root_path=root_path, name="2")
    assert obj_processor.get_xml_object_identifier().name == "2"
    with pytest.raises(ValueError, match=f"Unknown '{schema_type}' path '{root_path}' name '3'."):
        docs_processor.get_object_processor(schema_type=schema_type, root_path=root_path, name="3")

    # Check if image names exist.
    identifier1 = ObjectIdentifier(schema_type=schema_type, object_type=object_type, root_path=root_path, name="1")
    identifier2 = ObjectIdentifier(schema_type=schema_type, object_type=object_type, root_path=root_path, name="2")
    unknown_identifier = ObjectIdentifier(
        schema_type=schema_type, object_type=object_type, root_path=root_path, name="3"
    )

    assert docs_processor.is_object_name(identifier1)
    assert docs_processor.is_object_name(identifier2)
    assert not docs_processor.is_object_name(unknown_identifier)

    # Update image names.
    identifier1.new_name = str(uuid.uuid4())
    identifier2.new_name = str(uuid.uuid4())
    docs_processor.set_object_name(identifier1)
    docs_processor.set_object_name(identifier2)

    # Check updated image names.
    obj_processor = docs_processor.get_object_processor(
        schema_type=schema_type, root_path=root_path, name=identifier1.new_name
    )
    assert obj_processor.get_xml_object_identifier().name == identifier1.new_name
    obj_processor = docs_processor.get_object_processor(
        schema_type=schema_type, root_path=root_path, name=identifier2.new_name
    )
    assert obj_processor.get_xml_object_identifier().name == identifier2.new_name

    # Check if updated image names exist.
    identifier1.name = identifier1.new_name
    identifier2.name = identifier1.new_name
    assert docs_processor.is_object_name(identifier1)
    assert docs_processor.is_object_name(identifier2)
