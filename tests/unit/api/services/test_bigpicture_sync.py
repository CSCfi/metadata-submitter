"""Tests for packaging the metadata objects of a Bigpicture submission."""

import io
import json
import zipfile
from collections import defaultdict
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from lxml.etree import QName

from metadata_backend.api.models.models import File, Object
from metadata_backend.api.models.submission import Submission, SubmissionWorkflow
from metadata_backend.api.processors.xml.bigpicture import (
    BP_SAMPLE_SCHEMA,
    BP_XML_OBJECT_CONFIGS,
    BigpictureVersion,
)
from metadata_backend.api.processors.xml.datacite import DATACITE_OBJECT_TYPE, DATACITE_SCHEMA
from metadata_backend.api.processors.xml.processors import XmlProcessor
from metadata_backend.api.services.bigpicture import (
    BP_SYNC_FILES_PATH,
    BP_SYNC_METADATA_DIR,
    BigpictureSyncMetadataProvider,
)
from metadata_backend.database.postgres.services.file import FileService
from metadata_backend.database.postgres.services.object import ObjectService

BP_TEST_FILES_DIR = Path(__file__).parent.parent.parent.parent / "test_files" / "xml" / "bigpicture"

SUBMISSION_ID = "submission_1"


def _test_documents(version: BigpictureVersion) -> dict[str, list[str]]:
    """The metadata objects of the test submission, by object type."""

    documents: dict[str, list[str]] = defaultdict(list)
    for path in sorted((BP_TEST_FILES_DIR / version).glob("*.xml")):
        if path.name == f"{DATACITE_SCHEMA}.xml":
            # DataCite is one standalone document rather than a set of objects.
            documents[DATACITE_OBJECT_TYPE].append(path.read_text(encoding="utf-8"))
            continue
        for xml in XmlProcessor.parse_xml(path.read_text(encoding="utf-8")).getroot():
            object_type = BP_XML_OBJECT_CONFIGS[version].get_object_type(f"/{QName(xml.tag).localname}")
            documents[object_type].append(XmlProcessor.write_xml(xml))
    return documents


MOCK_FILES = [
    File(
        fileId="file_2",
        objectId="image_1",
        path="b.dcm.c4gh",
        bytes=200,
        checksumMethod="SHA256",
        unencryptedChecksum="a" * 64,
        encryptedChecksum="b" * 64,
    ),
    File(fileId="file_1", path="a.dcm.c4gh"),
]


EXPECTED_DOCUMENTS_2 = [
    f"{BP_SYNC_METADATA_DIR}/{name}.xml"
    for name in (
        "annotation",
        "datacite",
        "dataset",
        "image",
        "landing_page",
        "observation",
        "observer",
        "organisation",
        "policy",
        "rems",
        "sample",
        "staining",
    )
]
EXPECTED_DOCUMENTS_3 = [
    f"{BP_SYNC_METADATA_DIR}/{name}.xml"
    for name in (
        "annotation",
        "annotation_task",
        "annotator",
        "datacite",
        "dataset",
        "image",
        "landing_page",
        "observation",
        "observer",
        "ontology",
        "organisation",
        "policy",
        "rems",
        "sample",
        "staining",
    )
]


EXPECTED_FILES = [
    {"fileId": "file_1", "path": "a.dcm.c4gh"},
    {"fileId": "file_2", "objectId": "image_1", "path": "b.dcm.c4gh"},
]

EXPECTED_SAMPLE_TAGS = ("BIOLOGICAL_BEING", "BLOCK", "CASE", "SLIDE", "SPECIMEN")


def _provider(test_documents: dict[str, list[str]]) -> BigpictureSyncMetadataProvider:
    """A Bigpicture sync provider over a mocked object service."""

    async def get_objects(_: str, object_type: str | Sequence[str] | None = None) -> list[Object]:
        return [
            Object(name="1", objectId=object_type, objectType=object_type, submissionId=SUBMISSION_ID)
            for object_type in test_documents
        ]

    async def get_documents(_: str, object_type: str | Sequence[str] | None = None) -> AsyncIterator[str]:
        object_types = [object_type] if isinstance(object_type, str) else list(object_type or [])
        for one_object_type in object_types:
            for document in test_documents[one_object_type]:
                yield document

    async def get_files(*_: object, **__: object) -> AsyncIterator[File]:
        for file in MOCK_FILES:
            yield file

    object_service = cast(ObjectService, SimpleNamespace(get_objects=get_objects, get_documents=get_documents))
    file_service = cast(FileService, SimpleNamespace(get_files=get_files))
    return BigpictureSyncMetadataProvider(object_service, file_service)


@pytest.mark.parametrize(
    ("version", "expected_documents"),
    [(BigpictureVersion.V2_0, EXPECTED_DOCUMENTS_2), (BigpictureVersion.V3_0, EXPECTED_DOCUMENTS_3)],
)
async def test_metadata_archive(version, expected_documents):
    test_documents = _test_documents(version)
    assert set(test_documents) == {paths.object_type for paths in BP_XML_OBJECT_CONFIGS[version].object_paths} | {
        DATACITE_OBJECT_TYPE
    }

    submission = Submission(
        projectId="project",
        submissionId=SUBMISSION_ID,
        name="name",
        title="title",
        description="description",
        workflow=SubmissionWorkflow.BP,
        metadataVersion=version,
    )
    archive = await _provider(test_documents).get_metadata_archive(submission)

    with zipfile.ZipFile(io.BytesIO(archive)) as zip_file:
        # Check that the XML documents and the file list exist.
        assert sorted(zip_file.namelist()) == sorted([*expected_documents, BP_SYNC_FILES_PATH])

        # Check that sample XML tags exist.
        sample = zip_file.read(f"{BP_SYNC_METADATA_DIR}/{BP_SAMPLE_SCHEMA}.xml").decode()
        for tag in EXPECTED_SAMPLE_TAGS:
            assert f"<{tag} " in sample, tag

        # Check that DataCite is written as it is.
        datacite = zip_file.read(f"{BP_SYNC_METADATA_DIR}/{DATACITE_SCHEMA}.xml").decode()
        assert datacite == test_documents[DATACITE_OBJECT_TYPE][0]

        # Check that the files are listed by path, without the checksums and empty fields.
        assert json.loads(zip_file.read(BP_SYNC_FILES_PATH)) == EXPECTED_FILES
