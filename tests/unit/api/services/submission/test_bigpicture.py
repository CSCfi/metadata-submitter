"""Tests for Bigpicture submission service."""

import re

import pytest

from metadata_backend.api.exceptions import UserException
from metadata_backend.api.processors.xml.bigpicture import BP_DATASET_PATH, BP_DATASET_SCHEMA, BigpictureVersion
from metadata_backend.api.processors.xml.processors import XmlObjectProcessor
from metadata_backend.api.services.submission.bigpicture import (
    BigpictureObjectSubmissionService,
    validate_bigpicture_documents,
)
from metadata_backend.api.services.submission.submission import ObjectSubmission
from tests.utils import BP_ANNOTATION_1_FILE, BP_IMAGE_1_FILE, BP_IMAGE_2_FILE, bp_objects


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


def test_prepare_create_submission_uses_dataset_alias_as_name():
    """The submission name should be the dataset's unique alias."""

    objects, _ = bp_objects(is_update=False)
    processor, datacite, _ = BigpictureObjectSubmissionService._create_processor(objects)
    service = object.__new__(BigpictureObjectSubmissionService)
    service._processor = processor
    service._datacite = datacite
    submission = service.prepare_create_submission("PROJECT_1", "SUB_1")

    assert submission.name == "1"


def test_prepare_files_valid_image_and_annotation():
    """Valid BP objects should produce dataset-prefixed image and annotation file paths."""

    objects, _ = bp_objects(is_update=False)
    files = _prepare_files(objects, "SUB_1")

    paths = {f.path for f in files}
    expected_paths = {
        f"DATASET_SUB_1/{BP_IMAGE_1_FILE}.c4gh",
        f"DATASET_SUB_1/{BP_IMAGE_2_FILE}.c4gh",
        f"DATASET_SUB_1/{BP_ANNOTATION_1_FILE}.c4gh",
    }
    assert expected_paths == paths


def test_prepare_files_wrong_directory_raises():
    # Image files must be under IMAGES/IMAGE_{alias}.
    objects, _ = bp_objects(is_update=False)
    objects = _replace_object_document(
        objects,
        "image.xml",
        BP_IMAGE_1_FILE,
        "IMAGES/IMAGE_X/test.dcm",
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
        BP_ANNOTATION_1_FILE,
        "OTHER_DIR/test.geojson",
    )

    with pytest.raises(
        UserException, match="ANNOTATION file 'OTHER_DIR/test.geojson.c4gh' must be in directory 'ANNOTATIONS'."
    ):
        _prepare_files(objects)


def test_prepare_files_image_file_suffix():
    # Image files must have .dcm suffix.
    for invalid_file_path in ["test.tif", "test.tif.c4gh"]:
        objects, _ = bp_objects(is_update=False)
        objects = _replace_object_document(objects, "image.xml", "test.dcm", invalid_file_path)
        prepared_file_path = BigpictureObjectSubmissionService._prepare_file_path(invalid_file_path)
        with pytest.raises(
            UserException, match=f"Image file 'IMAGES/IMAGE_1/{prepared_file_path}' must have a .dcm extension"
        ):
            _prepare_files(objects)


def test_prepare_file_path_adds_suffix():
    # Files must have .c4gh suffix.
    assert "test.c4gh" == BigpictureObjectSubmissionService._prepare_file_path("test")
    assert "test.c4gh" == BigpictureObjectSubmissionService._prepare_file_path("test.c4gh")


def test_check_image_file_dir_invalid_dir():
    alias = "TEST"
    path = "IMAGES/INVALID/image"

    with pytest.raises(UserException) as exc:
        BigpictureObjectSubmissionService.check_image_file_dir(alias, path)

    assert f"Image file '{path}' must be in directory 'IMAGES/IMAGE_TEST'" in str(exc.value)


def test_check_image_file_dir_correct_dir():
    alias = "TEST"
    path = "IMAGES/IMAGE_TEST/image"
    BigpictureObjectSubmissionService.check_image_file_dir(alias, path)

    alias = "IMAGE_TEST"
    path = "IMAGES/IMAGE_TEST/image"
    BigpictureObjectSubmissionService.check_image_file_dir(alias, path)


@pytest.mark.parametrize("version", list(BigpictureVersion))
def test_validate_documents_adds_missing_dataset_references(version):
    """Image, annotation and observation references missing from the dataset are added in the correct place."""

    objects, _ = bp_objects(is_update=False, version=version)
    objects = [
        ObjectSubmission(
            filename=o.filename,
            document=re.sub(r"<(IMAGE|ANNOTATION|OBSERVATION)_REF [^>]*/>", "", o.document)
            if o.filename == "dataset.xml"
            else o.document,
        )
        for o in objects
    ]
    processor, _, _ = BigpictureObjectSubmissionService._create_processor(objects)

    dataset_name = processor.get_object_identifiers(BP_DATASET_SCHEMA)[0].name
    dataset_processor = processor.get_object_processor(BP_DATASET_SCHEMA, BP_DATASET_PATH, dataset_name)
    ref_tags = ["IMAGE_REF", "ANNOTATION_REF", "OBSERVATION_REF"]

    def dataset_ref_tags() -> list[str]:
        return [tag for tag in ref_tags if dataset_processor.root_element.find(tag) is not None]

    assert dataset_ref_tags() == []

    validate_bigpicture_documents(processor)

    assert dataset_ref_tags() == ref_tags
    # Validates the dataset XML against the XML schema.
    XmlObjectProcessor(dataset_processor.config, dataset_processor.xml)
