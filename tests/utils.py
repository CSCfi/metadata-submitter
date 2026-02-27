"Submission documents for unit, integration and performance tests."

import io
import json
import re
import uuid
from pathlib import Path
from typing import Any

from metadata_backend.api.json import to_json
from metadata_backend.api.models.submission import Submission
from metadata_backend.api.processors.models import ObjectIdentifier
from metadata_backend.api.processors.xml.bigpicture import (
    BP_ANNOTATION_OBJECT_TYPE,
    BP_ANNOTATION_PATH,
    BP_ANNOTATION_SCHEMA,
    BP_DATASET_OBJECT_TYPE,
    BP_DATASET_PATH,
    BP_DATASET_SCHEMA,
    BP_IMAGE_OBJECT_TYPE,
    BP_IMAGE_PATH,
    BP_IMAGE_SCHEMA,
    BP_LANDING_PAGE_OBJECT_TYPE,
    BP_LANDING_PAGE_PATH,
    BP_LANDING_PAGE_SCHEMA,
    BP_OBSERVATION_OBJECT_TYPE,
    BP_OBSERVATION_PATH,
    BP_OBSERVATION_SCHEMA,
    BP_OBSERVER_OBJECT_TYPE,
    BP_OBSERVER_PATH,
    BP_OBSERVER_SCHEMA,
    BP_ORGANISATION_OBJECT_TYPE,
    BP_ORGANISATION_PATH,
    BP_ORGANISATION_SCHEMA,
    BP_POLICY_OBJECT_TYPE,
    BP_POLICY_PATH,
    BP_POLICY_SCHEMA,
    BP_REMS_OBJECT_TYPE,
    BP_REMS_PATH,
    BP_REMS_SCHEMA,
    BP_SAMPLE_BIOLOGICAL_BEING_OBJECT_TYPE,
    BP_SAMPLE_BIOLOGICAL_BEING_PATH,
    BP_SAMPLE_BLOCK_OBJECT_TYPE,
    BP_SAMPLE_BLOCK_PATH,
    BP_SAMPLE_CASE_OBJECT_TYPE,
    BP_SAMPLE_CASE_PATH,
    BP_SAMPLE_SCHEMA,
    BP_SAMPLE_SLIDE_OBJECT_TYPE,
    BP_SAMPLE_SLIDE_PATH,
    BP_SAMPLE_SPECIMEN_OBJECT_TYPE,
    BP_SAMPLE_SPECIMEN_PATH,
    BP_STAINING_OBJECT_TYPE,
    BP_STAINING_PATH,
    BP_STAINING_SCHEMA,
)
from metadata_backend.api.services.submission.bigpicture import BigPictureObjectSubmissionService
from metadata_backend.api.services.submission.submission import ObjectSubmission

DATACITE_XML = "datacite.xml"

TEST_FILES_ROOT = Path(__file__).parent / "test_files"

SD_SUBMISSION_DIR = TEST_FILES_ROOT / "submission"
SD_SUBMISSION = TEST_FILES_ROOT / "submission" / "submission.json"

BP_SUBMISSION_DIR = TEST_FILES_ROOT / "xml" / "bigpicture"
BP_UPDATE_DIR = BP_SUBMISSION_DIR / "update"

ObjectNames = dict[str, dict[str, dict[str, str]]]


def bp_objects(is_update: bool) -> tuple[list[ObjectSubmission], dict[str, Path]]:
    """
    Get BP XML test files.

    :param is_update: If true then updated XML files are used.
    :return: ObjectSubmission list, and list of file names and paths.
    """

    files = {p.name: p for p in BP_SUBMISSION_DIR.iterdir() if p.is_file()}
    if is_update:
        # Use update files.
        files.update({p.name: p for p in BP_UPDATE_DIR.iterdir() if p.is_file()})

    # Changes other XML files except Datacite XML.
    objects: list[ObjectSubmission] = []
    for name, file in files.items():
        if name != DATACITE_XML:
            document = file.read_text(encoding="utf-8")
            objects.append(ObjectSubmission(filename=file.name, document=document))

    return objects, files


def _bp_submission_documents(
    submission_name: str | None = None,
    object_names: ObjectNames | None = None,
    is_update: bool = False,
    is_datacite: bool = False,
) -> tuple[str, ObjectNames, dict[str, io.BytesIO]]:
    """
    Read BP XML test files, assign unique submission name and object names while preserving provided object names.

    Assigns a unique submission name and unique object names. The original object names in the
    XML files are suffixed with an underscore and a generated UUID4.

    :param submission_name: Use the provided submission name instead of generating a new one.
    :param object_names: Use the provided object names instead of generating a new ones
    :param is_update: If true then updated XML files are used.
    :param is_datacite: If true then returns the Datacite XML file.
    :return: submission name, object_names, and dictionary of file names and IO bytes.
    """

    objects, files = bp_objects(is_update)
    processor, _ = BigPictureObjectSubmissionService._create_processor(objects)

    new_object_names: ObjectNames = {}

    # Change submission name.
    submission_name = submission_name or f"test_{uuid.uuid4()}"
    dataset_processor = processor.get_object_processor(BP_DATASET_SCHEMA, BP_DATASET_PATH, "1")
    for elem in dataset_processor.xml.getroot().findall(".//SHORT_NAME"):
        elem.text = submission_name

    def unique_object_name(_name: str) -> str:
        """Extract digits at the start of _id (before optional '_'), append '_' + value, and return the result."""
        match = re.match(r"^(\d+)", _name)
        if match:
            return f"{match.group(1)}_{uuid.uuid4()}"
        else:
            raise ValueError(f"Invalid id format: {_name}")

    def change_object_name(_schema_type: str, _object_type: str, _root_path: str, _original_object_name: str):
        keep_object_name = None
        if object_names is not None:
            if _schema_type in object_names:
                if _object_type in object_names[_schema_type]:
                    if _original_object_name in object_names[_schema_type][_object_type]:
                        keep_object_name = object_names[_schema_type][_object_type][_original_object_name]
        if keep_object_name is None:
            # Create a new unique object name,
            new_object_name = unique_object_name(_original_object_name)
        else:
            # Keep using a previously created unique object name.
            new_object_name = keep_object_name
        new_object_names.setdefault(_schema_type, {}).setdefault(_object_type, {})[_original_object_name] = (
            new_object_name
        )
        identifier = ObjectIdentifier(
            schema_type=_schema_type,
            object_type=_object_type,
            root_path=_root_path,
            name=_original_object_name,
            new_name=new_object_name,
        )
        if processor.is_object_name(identifier):
            processor.set_object_name(identifier)

    # Change object names.
    change_object_name(BP_DATASET_SCHEMA, BP_DATASET_OBJECT_TYPE, BP_DATASET_PATH, "1")
    change_object_name(BP_POLICY_SCHEMA, BP_POLICY_OBJECT_TYPE, BP_POLICY_PATH, "1")
    change_object_name(BP_IMAGE_SCHEMA, BP_IMAGE_OBJECT_TYPE, BP_IMAGE_PATH, "1")
    change_object_name(BP_IMAGE_SCHEMA, BP_IMAGE_OBJECT_TYPE, BP_IMAGE_PATH, "2")  # not in update
    change_object_name(BP_IMAGE_SCHEMA, BP_IMAGE_OBJECT_TYPE, BP_IMAGE_PATH, "3")  # in update
    change_object_name(BP_ANNOTATION_SCHEMA, BP_ANNOTATION_OBJECT_TYPE, BP_ANNOTATION_PATH, "1")
    change_object_name(BP_OBSERVATION_SCHEMA, BP_OBSERVATION_OBJECT_TYPE, BP_OBSERVATION_PATH, "1")
    change_object_name(BP_OBSERVER_SCHEMA, BP_OBSERVER_OBJECT_TYPE, BP_OBSERVER_PATH, "1")
    change_object_name(BP_SAMPLE_SCHEMA, BP_SAMPLE_BIOLOGICAL_BEING_OBJECT_TYPE, BP_SAMPLE_BIOLOGICAL_BEING_PATH, "1")
    change_object_name(BP_SAMPLE_SCHEMA, BP_SAMPLE_SLIDE_OBJECT_TYPE, BP_SAMPLE_SLIDE_PATH, "1")
    change_object_name(BP_SAMPLE_SCHEMA, BP_SAMPLE_SPECIMEN_OBJECT_TYPE, BP_SAMPLE_SPECIMEN_PATH, "1")
    change_object_name(BP_SAMPLE_SCHEMA, BP_SAMPLE_BLOCK_OBJECT_TYPE, BP_SAMPLE_BLOCK_PATH, "1")
    change_object_name(BP_SAMPLE_SCHEMA, BP_SAMPLE_CASE_OBJECT_TYPE, BP_SAMPLE_CASE_PATH, "1")
    change_object_name(BP_STAINING_SCHEMA, BP_STAINING_OBJECT_TYPE, BP_STAINING_PATH, "1")
    change_object_name(BP_LANDING_PAGE_SCHEMA, BP_LANDING_PAGE_OBJECT_TYPE, BP_LANDING_PAGE_PATH, "1")
    change_object_name(BP_REMS_SCHEMA, BP_REMS_OBJECT_TYPE, BP_REMS_PATH, "1")
    change_object_name(BP_ORGANISATION_SCHEMA, BP_ORGANISATION_OBJECT_TYPE, BP_ORGANISATION_PATH, "1")

    data = {}
    for doc_processor in processor.xml_processors:
        xml = doc_processor.xml
        xml_bytes = io.BytesIO()
        xml.write(xml_bytes, encoding="utf-8", xml_declaration=False)
        xml_bytes.seek(0)
        data[f"{doc_processor.schema_type}.xml"] = xml_bytes

    if is_datacite:
        data[DATACITE_XML] = io.BytesIO(files[DATACITE_XML].read_bytes())

    return submission_name, new_object_names, data


def bp_submission_documents(
    *, is_datacite: bool, submission_name: str | None = None
) -> tuple[str, ObjectNames, dict[str, io.BytesIO]]:
    """
    Get BP XML test files for a new submission.

    Assigns a unique submission name and object names. The original object names in the
    XML files are suffixed with an underscore and a generated UUID4.

    :param submission_name: The submission name.
    :param is_datacite: If true then returns the Datacite XML file.
    :return: submission name, object_names, and dictionary of file names and IO bytes.
    """

    return _bp_submission_documents(submission_name=submission_name, is_update=False, is_datacite=is_datacite)


def bp_update_documents(
    submission_name: str, object_names: ObjectNames, is_datacite: bool
) -> tuple[str, ObjectNames, dict[str, io.BytesIO]]:
    """
    Get BP XML test files for a submission update.

    Assigns unique names for any new objects. The original object names in the
    XML files are suffixed with an underscore and a generated UUID4.

    :param submission_name: The submission name.
    :param object_names: The object names in the original submission.
    :param is_datacite: If true then returns the Datacite XML file.
    :return: submission name, object_names, and dictionary of file names and IO bytes.
    """

    return _bp_submission_documents(submission_name, object_names, is_update=True, is_datacite=is_datacite)


def sd_submission_document(submission: Submission | dict[str, Any] | None = None) -> dict[str, io.BytesIO]:
    """
    Get SD submission JSON for a new submission.

    :param submission: Use the provided submission document instead of using the test file.
    :return: dictionary of file names and IO bytes.
    """

    if submission:
        data = io.BytesIO(to_json(submission).encode("utf-8"))
        data.seek(0)
    else:
        file_path = SD_SUBMISSION_DIR / "submission.json"
        with open(file_path, "rb") as f:
            data = io.BytesIO(f.read())

    return {"submission.json": data}


def sd_submission_dict() -> dict[str, Any]:
    """
    Get SD submission metadata for a new submission as a dictionary.

    :return: SD submission metadata.
    """

    return json.loads(SD_SUBMISSION.read_text())
