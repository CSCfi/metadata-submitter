"""Tests for Bigpicture API service."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from metadata_backend.api.exceptions import SystemException
from metadata_backend.api.models.submission import Submission, SubmissionWorkflow
from metadata_backend.api.processors.xml.bigpicture import (
    BP_LANDING_PAGE_OBJECT_TYPE,
    BP_SAMPLE_OBJECT_TYPES,
    BP_XML_SCHEMA_3_DIR,
)
from metadata_backend.api.services.bigpicture import (
    get_bp_dataset_dir,
    get_bp_ingested_dataset_root,
    get_bp_metadata_file_paths,
    get_bp_metadata_file_replacements,
    upload_bp_metadata_xmls,
)
from metadata_backend.api.services.crypt import Crypt4GHPublicKeyProvider
from metadata_backend.api.services.file import S3InboxSDAService


def _submission(submission_id: str, *, metadata_version: str = "2.0", imported: bool | None = None) -> Submission:
    return Submission(
        projectId="project",
        submissionId=submission_id,
        name="name",
        title="title",
        description="description",
        workflow=SubmissionWorkflow.BP,
        metadataVersion=metadata_version,
        imported=imported,
    )


@pytest.mark.parametrize("with_optional", [True, False])
async def test_upload_bp_metadata_xmls_v2(with_optional):
    submission_id = "123"
    file_provider = S3InboxSDAService(AsyncMock(), AsyncMock(spec=Crypt4GHPublicKeyProvider))
    file_provider._add_file_to_bucket = AsyncMock()  # type: ignore[method-assign]

    object_docs: dict[str, list[str]] = {
        "dataset": ["<DATASET><METADATA_STANDARD>2.0.0</METADATA_STANDARD></DATASET>"],
        "policy": ["<POLICY/>"],
        "image": ["<IMAGE/>"],
        "annotation": ["<ANNOTATION/>"],
        "observation": ["<OBSERVATION/>"],
        "observer": ["<OBSERVER/>"],
        "staining": ["<STAINING/>"],
        "landing_page": [
            '<LANDING_PAGE alias="1"><DATASET_REF alias="1"/><ATTRIBUTES>'
            "<STRING_ATTRIBUTE><TAG>test</TAG><VALUE>test</VALUE></STRING_ATTRIBUTE>"
            "</ATTRIBUTES></LANDING_PAGE>"
        ],
        "organisation": ["<ORGANISATION/>"],
        "rems": ["<REMS/>"],
        "datacite": ["<resource/>"],
        BP_SAMPLE_OBJECT_TYPES[0]: ['<BIOLOGICAL_BEING alias="1"/>'],
        BP_SAMPLE_OBJECT_TYPES[1]: [
            '<SLIDE alias="1"><CREATED_FROM_REF alias="1"/><STAINING_INFORMATION_REF alias="1"/></SLIDE>'
        ],
    }
    # Annotation and observer objects are optional.
    if not with_optional:
        del object_docs["annotation"], object_docs["observer"]

    def get_documents(_submission_id: str, object_type: str | tuple[str, ...]):
        async def _iter():
            if isinstance(object_type, tuple):
                for sample_type in object_type:
                    for xml in object_docs.get(sample_type, []):
                        yield xml
                return

            for xml in object_docs.get(object_type, []):
                yield xml

        return _iter()

    services = SimpleNamespace(
        file_provider=file_provider,
        file=SimpleNamespace(is_file_by_path=AsyncMock(return_value=False), add_file=AsyncMock()),
        submission=SimpleNamespace(
            get_bucket=AsyncMock(return_value="test-bucket"),
            get_submission_by_id=AsyncMock(return_value=_submission(submission_id, metadata_version="2.0")),
        ),
        registration=SimpleNamespace(
            get_registration=AsyncMock(
                return_value=SimpleNamespace(dataciteUrl="https://doi.test", remsUrl="https://rems.test")
            )
        ),
        object=SimpleNamespace(get_documents=get_documents),
    )

    with patch("metadata_backend.api.services.bigpicture.XmlProcessor.validate_schema"):
        await upload_bp_metadata_xmls(services, submission_id, "request-user", "oidc-token")

    expected_keys = {
        "DATASET_123/METADATA/dataset.xml.c4gh",
        "DATASET_123/METADATA/policy.xml.c4gh",
        "DATASET_123/METADATA/image.xml.c4gh",
        "DATASET_123/METADATA/annotation.xml.c4gh",
        "DATASET_123/METADATA/observation.xml.c4gh",
        "DATASET_123/METADATA/observer.xml.c4gh",
        "DATASET_123/METADATA/sample.xml.c4gh",
        "DATASET_123/METADATA/staining.xml.c4gh",
        "DATASET_123/LANDING_PAGE/landing_page.xml.c4gh",
    }
    if not with_optional:
        expected_keys -= {"DATASET_123/METADATA/annotation.xml.c4gh", "DATASET_123/METADATA/observer.xml.c4gh"}

    assert file_provider._add_file_to_bucket.await_count == len(expected_keys)

    uploaded_keys = {call.kwargs["object_key"] for call in file_provider._add_file_to_bucket.await_args_list}
    assert uploaded_keys == expected_keys

    assert services.file.add_file.await_count == len(expected_keys)
    added_paths = {call.args[0].path for call in services.file.add_file.await_args_list}
    assert added_paths == expected_keys

    uploaded_by_key = {
        call.kwargs["object_key"]: call.kwargs["body"].decode("utf-8")
        for call in file_provider._add_file_to_bucket.await_args_list
    }

    assert "<DATASET_SET>" in uploaded_by_key["DATASET_123/METADATA/dataset.xml.c4gh"]
    assert "<SAMPLE_SET>" in uploaded_by_key["DATASET_123/METADATA/sample.xml.c4gh"]
    assert '<BIOLOGICAL_BEING alias="1"/>' in uploaded_by_key["DATASET_123/METADATA/sample.xml.c4gh"]
    assert '<SLIDE alias="1">' in uploaded_by_key["DATASET_123/METADATA/sample.xml.c4gh"]

    landing_page_xml = uploaded_by_key["DATASET_123/LANDING_PAGE/landing_page.xml.c4gh"]
    assert "<LANDING_PAGE_SET>" in landing_page_xml
    assert "<REMS_ACCESS_LINK>https://rems.test</REMS_ACCESS_LINK>" in landing_page_xml
    assert "<TAG>doi</TAG>" in landing_page_xml
    assert "<VALUE>https://doi.test</VALUE>" in landing_page_xml


async def test_upload_bp_metadata_xmls_v3():
    submission_id = "123"
    file_provider = S3InboxSDAService(AsyncMock(), AsyncMock(spec=Crypt4GHPublicKeyProvider))
    file_provider._add_file_to_bucket = AsyncMock()  # type: ignore[method-assign]

    object_docs: dict[str, list[str]] = {
        "dataset": ["<DATASET><METADATA_STANDARD>3.0.0</METADATA_STANDARD></DATASET>"],
        "policy": ["<POLICY/>"],
        "image": ["<IMAGE/>"],
        "annotation": ["<ANNOTATION/>"],
        "annotator": ['<ANNOTATOR alias="1"/>'],
        "ontology": ['<ONTOLOGY alias="1"/>'],
        "annotation_task": ['<ANNOTATION_TASK alias="1"/>'],
        "observation": ["<OBSERVATION/>"],
        "observer": ["<OBSERVER/>"],
        "staining": ["<STAINING/>"],
        "landing_page": [
            '<LANDING_PAGE alias="1"><DATASET_REF alias="1"/><ATTRIBUTES>'
            "<STRING_ATTRIBUTE><TAG>test</TAG><VALUE>test</VALUE></STRING_ATTRIBUTE>"
            "</ATTRIBUTES></LANDING_PAGE>"
        ],
        "organisation": ["<ORGANISATION/>"],
        "rems": ["<REMS/>"],
        "datacite": ["<resource/>"],
        BP_SAMPLE_OBJECT_TYPES[0]: ['<BIOLOGICAL_BEING alias="1"/>'],
        BP_SAMPLE_OBJECT_TYPES[1]: [
            '<SLIDE alias="1"><CREATED_FROM_REF alias="1"/><STAINING_INFORMATION_REF alias="1"/></SLIDE>'
        ],
    }

    def get_documents(_submission_id: str, object_type: str | tuple[str, ...]):
        async def _iter():
            if isinstance(object_type, tuple):
                for sample_type in object_type:
                    for xml in object_docs.get(sample_type, []):
                        yield xml
                return

            for xml in object_docs.get(object_type, []):
                yield xml

        return _iter()

    services = SimpleNamespace(
        file_provider=file_provider,
        file=SimpleNamespace(is_file_by_path=AsyncMock(return_value=False), add_file=AsyncMock()),
        submission=SimpleNamespace(
            get_bucket=AsyncMock(return_value="test-bucket"),
            get_submission_by_id=AsyncMock(return_value=_submission(submission_id, metadata_version="3.0")),
        ),
        registration=SimpleNamespace(
            get_registration=AsyncMock(
                return_value=SimpleNamespace(dataciteUrl="https://doi.test", remsUrl="https://rems.test")
            )
        ),
        object=SimpleNamespace(get_documents=get_documents),
    )

    with patch("metadata_backend.api.services.bigpicture.XmlProcessor.validate_schema") as validate_schema:
        await upload_bp_metadata_xmls(services, submission_id, "request-user", "oidc-token")

    # Every XML is validated against the 3.0 schemas.
    assert {call.args[1] for call in validate_schema.call_args_list} == {str(BP_XML_SCHEMA_3_DIR)}

    expected_keys = {
        "DATASET_123/METADATA/dataset.xml.c4gh",
        "DATASET_123/METADATA/policy.xml.c4gh",
        "DATASET_123/METADATA/image.xml.c4gh",
        "DATASET_123/METADATA/annotation.xml.c4gh",
        "DATASET_123/METADATA/annotator.xml.c4gh",
        "DATASET_123/METADATA/ontology.xml.c4gh",
        "DATASET_123/METADATA/annotation_task.xml.c4gh",
        "DATASET_123/METADATA/observation.xml.c4gh",
        "DATASET_123/METADATA/observer.xml.c4gh",
        "DATASET_123/METADATA/sample.xml.c4gh",
        "DATASET_123/METADATA/staining.xml.c4gh",
        "DATASET_123/LANDING_PAGE/landing_page.xml.c4gh",
    }

    assert file_provider._add_file_to_bucket.await_count == len(expected_keys)

    uploaded_keys = {call.kwargs["object_key"] for call in file_provider._add_file_to_bucket.await_args_list}
    assert uploaded_keys == expected_keys

    assert services.file.add_file.await_count == len(expected_keys)
    added_paths = {call.args[0].path for call in services.file.add_file.await_args_list}
    assert added_paths == expected_keys

    uploaded_by_key = {
        call.kwargs["object_key"]: call.kwargs["body"].decode("utf-8")
        for call in file_provider._add_file_to_bucket.await_args_list
    }

    assert "<DATASET_SET>" in uploaded_by_key["DATASET_123/METADATA/dataset.xml.c4gh"]
    assert "<SAMPLE_SET>" in uploaded_by_key["DATASET_123/METADATA/sample.xml.c4gh"]
    assert '<BIOLOGICAL_BEING alias="1"/>' in uploaded_by_key["DATASET_123/METADATA/sample.xml.c4gh"]
    assert '<SLIDE alias="1">' in uploaded_by_key["DATASET_123/METADATA/sample.xml.c4gh"]
    assert "<ANNOTATOR_SET>" in uploaded_by_key["DATASET_123/METADATA/annotator.xml.c4gh"]
    assert "<ONTOLOGY_SET>" in uploaded_by_key["DATASET_123/METADATA/ontology.xml.c4gh"]
    assert "<ANNOTATION_TASK_SET>" in uploaded_by_key["DATASET_123/METADATA/annotation_task.xml.c4gh"]

    landing_page_xml = uploaded_by_key["DATASET_123/LANDING_PAGE/landing_page.xml.c4gh"]
    assert "<LANDING_PAGE_SET>" in landing_page_xml
    assert "<REMS_ACCESS_LINK>https://rems.test</REMS_ACCESS_LINK>" in landing_page_xml
    assert "<TAG>doi</TAG>" in landing_page_xml
    assert "<VALUE>https://doi.test</VALUE>" in landing_page_xml


async def test_upload_bp_metadata_xmls_raises_on_upload_error():
    """Upload errors in BP metadata upload helper should fail publish flow."""

    file_provider = S3InboxSDAService(AsyncMock(), AsyncMock(spec=Crypt4GHPublicKeyProvider))
    file_provider._add_file_to_bucket = AsyncMock(side_effect=SystemException("upload failed"))  # type: ignore[method-assign]
    services = SimpleNamespace(
        file_provider=file_provider,
        file=SimpleNamespace(is_file_by_path=AsyncMock(return_value=False), add_file=AsyncMock()),
    )

    xmls = {"DATASET_123/METADATA/dataset.xml.c4gh": "<DATASET_SET/>"}
    with patch("metadata_backend.api.services.bigpicture.generate_bp_metadata_xmls", AsyncMock(return_value=xmls)):
        with pytest.raises(SystemException, match="upload failed"):
            await upload_bp_metadata_xmls(services, "123", "request-user", "oidc-token")

    services.file.add_file.assert_not_awaited()


@pytest.mark.parametrize(
    "paths, root",
    [
        (["ROOT/METADATA/dataset.xml.c4gh", "ROOT/IMAGES/IMAGE_1/test.dcm.c4gh"], "ROOT"),
        (["ROOT/a.dcm.c4gh", "OTHER/b.dcm.c4gh"], None),
        (["ROOT/a.dcm.c4gh", "b.dcm.c4gh"], None),
        (["/METADATA/dataset.xml.c4gh", "/IMAGES/IMAGE_1/test.dcm.c4gh"], None),
        ([], None),
    ],
)
def test_get_bp_ingested_dataset_root(paths, root):
    assert get_bp_ingested_dataset_root(paths) == root


def test_get_bp_dataset_dir():
    paths = ["ROOT/IMAGES/IMAGE_1/test.dcm.c4gh", "ROOT/METADATA/dataset.xml.c4gh"]
    assert get_bp_dataset_dir(_submission("123"), paths) == "DATASET_123"

    submission = _submission("123", imported=True)
    assert get_bp_dataset_dir(submission, paths) == "ROOT"

    with pytest.raises(SystemException, match="not under one root directory"):
        get_bp_dataset_dir(submission, ["ROOT/a.dcm.c4gh", "OTHER/b.dcm.c4gh"])


def test_get_bp_metadata_file_replacements():
    data_file = "ROOT/IMAGES/IMAGE_1/test.dcm.c4gh"
    thumbnail = "ROOT/LANDING_PAGE/THUMBNAILS/thumb.jpg.c4gh"
    submission = {
        "data-file-id": data_file,
        # Removed outside SD Submit after import. Does not affect import ingest that only replaces ML files.
        "removed-data-file-id": "ROOT/IMAGES/IMAGE_2/test2.dcm.c4gh",
        "thumbnail-id": thumbnail,
        "new-dataset-id": "ROOT/METADATA/dataset.xml.c4gh",
        "new-landing-page-id": "ROOT/LANDING_PAGE/landing_page.xml.c4gh",
    }
    sda = {
        "data-file-id": data_file,
        "thumbnail-id": thumbnail,
        # The old XML is replaced even without the .c4gh suffix.
        "old-dataset-id": "ROOT/METADATA/dataset.xml",
        # Added outside SD Submit after import. Does not affect import ingest that only replaces ML files.
        # A data file.
        "other-data-file-id": "ROOT/IMAGES/IMAGE_3/test3.dcm.c4gh",
        # A metadata XML not being replaced.
        "not-replaced-xml-id": "ROOT/METADATA/annotation.xml.c4gh",
        # A metadata XML under another root directory.
        "other-root-xml-id": "OTHER/METADATA/dataset.xml.c4gh",
    }

    # Only the new XMLs are added, and only the old XML they replace is removed.
    replacements = get_bp_metadata_file_replacements(submission, sda)
    assert replacements.new_accessions == ["new-dataset-id", "new-landing-page-id"]
    assert replacements.old_accessions == ["old-dataset-id"]

    # Once the old XML is removed and the new ones added, there is nothing left to do
    del sda["old-dataset-id"]
    sda["new-dataset-id"] = submission["new-dataset-id"]
    sda["new-landing-page-id"] = submission["new-landing-page-id"]
    replacements = get_bp_metadata_file_replacements(submission, sda)
    assert replacements.new_accessions == []
    assert replacements.old_accessions == []


def test_get_bp_metadata_file_paths():
    assert get_bp_metadata_file_paths([BP_LANDING_PAGE_OBJECT_TYPE]) == {"LANDING_PAGE/landing_page.xml"}
    assert "METADATA/dataset.xml" in get_bp_metadata_file_paths()
