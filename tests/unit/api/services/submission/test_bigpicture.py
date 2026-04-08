"""Tests for Bigpicture submission service."""

import pytest

from metadata_backend.api.exceptions import UserException
from metadata_backend.api.services.submission.bigpicture import BigpictureObjectSubmissionService
from metadata_backend.api.services.submission.submission import ObjectSubmission
from tests.utils import bp_objects


def _replace_object_document(
    objects: list[ObjectSubmission],
    filename: str,
    old_value: str,
    new_value: str,
) -> list[ObjectSubmission]:
    """Return objects with one document updated via string replacement."""

    updated: list[ObjectSubmission] = []
    replaced = False

    for obj in objects:
        if obj.filename == filename:
            if old_value not in obj.document:
                raise AssertionError(f"Expected '{old_value}' in {filename} fixture.")
            updated.append(ObjectSubmission(filename=obj.filename, document=obj.document.replace(old_value, new_value)))
            replaced = True
        else:
            updated.append(obj)

    if not replaced:
        raise AssertionError(f"Object fixture '{filename}' not found.")

    return updated


def _prepare_files(objects: list[ObjectSubmission], submission_id: str = "SUB_1"):
    """Create processor from full BP object set and run prepare_files."""

    processor, _, _ = BigpictureObjectSubmissionService._create_processor(objects)
    service = object.__new__(BigpictureObjectSubmissionService)
    service._processor = processor
    return service.prepare_files(submission_id)


def test_prepare_files_valid_image_and_annotation():
    """Valid BP objects should produce dataset-prefixed image and annotation file paths."""

    objects, _ = bp_objects(is_update=False)
    files = _prepare_files(objects, "SUB_1")

    paths = {f.path for f in files}
    expected_paths = {
        "DATASET_SUB_1/IMAGES/IMAGE_1/test.dcm.c4gh",
        "DATASET_SUB_1/IMAGES/IMAGE_2/test2.dcm.c4gh",
        "DATASET_SUB_1/ANNOTATIONS/test.geojson.c4gh",
    }
    assert expected_paths == paths


def test_prepare_files_wrong_directory_raises():
    # Image files must be under IMAGES/IMAGE_{alias}.
    objects, _ = bp_objects(is_update=False)
    objects = _replace_object_document(
        objects,
        "image.xml",
        "IMAGES/IMAGE_1/test.dcm.c4gh",
        "IMAGES/IMAGE_X/test.dcm.c4gh",
    )

    with pytest.raises(
        UserException, match="Image file 'IMAGES/IMAGE_X/test.dcm.c4gh' must be in directory 'IMAGES/IMAGE_1'."
    ):
        _prepare_files(objects)

    # Annotation files must be under ANNOTATIONS/.
    objects, _ = bp_objects(is_update=False)
    objects = _replace_object_document(
        objects,
        "annotation.xml",
        "ANNOTATIONS/test.geojson.c4gh",
        "OTHER_DIR/test.geojson.c4gh",
    )

    with pytest.raises(
        UserException, match="Annotation file 'OTHER_DIR/test.geojson.c4gh' must be in directory 'ANNOTATIONS'."
    ):
        _prepare_files(objects)


def test_prepare_files_wrong_extension_raises():
    # Image files must have .dcm (optionally .c4gh suffix).
    objects, _ = bp_objects(is_update=False)
    objects = _replace_object_document(objects, "image.xml", "test.dcm.c4gh", "test.tif.c4gh")

    with pytest.raises(UserException, match="Image file 'IMAGES/IMAGE_1/test.tif.c4gh' must have a .dcm extension"):
        _prepare_files(objects)

    # Annotation files must have .geojson (optionally .c4gh suffix).
    objects, _ = bp_objects(is_update=False)
    objects = _replace_object_document(objects, "annotation.xml", "test.geojson.c4gh", "test.json.c4gh")

    with pytest.raises(
        UserException, match="Annotation file 'ANNOTATIONS/test.json.c4gh' must have a .geojson extension"
    ):
        _prepare_files(objects)
