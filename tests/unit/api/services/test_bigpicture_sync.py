"""Tests for packaging the metadata objects of a Bigpicture submission."""

import io
import zipfile
from collections import defaultdict
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from lxml.etree import QName

from metadata_backend.api.models.models import Object
from metadata_backend.api.processors.xml.bigpicture import BP_SAMPLE_SCHEMA, BP_XML_OBJECT_CONFIG
from metadata_backend.api.processors.xml.datacite import DATACITE_OBJECT_TYPE, DATACITE_SCHEMA
from metadata_backend.api.processors.xml.processors import XmlProcessor
from metadata_backend.api.services.bigpicture import (
    BP_SYNC_METADATA_DIR,
    BigpictureSyncMetadataProvider,
)
from metadata_backend.database.postgres.services.object import ObjectService

BP_SUBMISSION_DIR = Path(__file__).parent.parent.parent.parent / "test_files" / "xml" / "bigpicture"

SUBMISSION_ID = "submission_1"


def _test_documents() -> dict[str, list[str]]:
    """The metadata objects of the test submission, by object type."""

    documents: dict[str, list[str]] = defaultdict(list)
    for path in sorted(BP_SUBMISSION_DIR.glob("*.xml")):
        if path.name == f"{DATACITE_SCHEMA}.xml":
            # DataCite is one standalone document rather than a set of objects.
            documents[DATACITE_OBJECT_TYPE].append(path.read_text(encoding="utf-8"))
            continue
        for xml in XmlProcessor.parse_xml(path.read_text(encoding="utf-8")).getroot():
            object_type = BP_XML_OBJECT_CONFIG.get_object_type(f"/{QName(xml.tag).localname}")
            documents[object_type].append(XmlProcessor.write_xml(xml))
    return documents


TEST_DOCUMENTS = _test_documents()

EXPECTED_DOCUMENTS = [
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

EXPECTED_SAMPLE_TAGS = ("BIOLOGICAL_BEING", "BLOCK", "CASE", "SLIDE", "SPECIMEN")


def _provider() -> BigpictureSyncMetadataProvider:
    """A Bigpicture sync provider over a mocked object service."""

    async def get_objects(_: str, object_type: str | Sequence[str] | None = None) -> list[Object]:
        return [
            Object(name="1", objectId=object_type, objectType=object_type, submissionId=SUBMISSION_ID)
            for object_type in TEST_DOCUMENTS
        ]

    async def get_xml_documents(_: str, object_type: str | Sequence[str] | None = None) -> AsyncIterator[str]:
        object_types = [object_type] if isinstance(object_type, str) else list(object_type or [])
        for one_object_type in object_types:
            for document in TEST_DOCUMENTS[one_object_type]:
                yield document

    object_service = cast(ObjectService, SimpleNamespace(get_objects=get_objects, get_xml_documents=get_xml_documents))
    return BigpictureSyncMetadataProvider(object_service)


async def test_metadata_archive():
    assert set(TEST_DOCUMENTS) == {paths.object_type for paths in BP_XML_OBJECT_CONFIG.object_paths} | {
        DATACITE_OBJECT_TYPE
    }

    archive = await _provider().get_metadata_archive(SUBMISSION_ID)

    with zipfile.ZipFile(io.BytesIO(archive)) as zip_file:
        # Check that expected XML documents exist.
        assert sorted(zip_file.namelist()) == EXPECTED_DOCUMENTS

        # Check that sample XML tags exist.
        sample = zip_file.read(f"{BP_SYNC_METADATA_DIR}/{BP_SAMPLE_SCHEMA}.xml").decode()
        for tag in EXPECTED_SAMPLE_TAGS:
            assert f"<{tag} " in sample, tag

        # Check that DataCite is written as it is.
        datacite = zip_file.read(f"{BP_SYNC_METADATA_DIR}/{DATACITE_SCHEMA}.xml").decode()
        assert datacite == TEST_DOCUMENTS[DATACITE_OBJECT_TYPE][0]
