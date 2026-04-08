"""Tests for Bigpicture API service."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from metadata_backend.api.exceptions import SystemException
from metadata_backend.api.processors.xml.bigpicture import BP_SAMPLE_OBJECT_TYPES
from metadata_backend.api.services.bigpicture import upload_bp_metadata_xmls
from metadata_backend.api.services.file import S3InboxSDAService


async def test_upload_bp_metadata_xmls_uses_expected_object_keys_and_payloads():
    """BP metadata upload helper should upload plaintext XML to expected DATASET_{id}/METADATA keys."""

    submission_id = "123"
    file_provider = S3InboxSDAService(AsyncMock())
    file_provider._add_file_to_bucket = AsyncMock()  # type: ignore[method-assign]

    object_docs: dict[str, list[str]] = {
        "dataset": ["<DATASET/>"],
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

    def get_xml_documents(_submission_id: str, object_type: str | tuple[str, ...]):
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
        submission=SimpleNamespace(get_bucket=AsyncMock(return_value="test-bucket")),
        registration=SimpleNamespace(
            get_registration=AsyncMock(
                return_value=SimpleNamespace(dataciteUrl="https://doi.test", remsUrl="https://rems.test")
            )
        ),
        object=SimpleNamespace(get_xml_documents=get_xml_documents),
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
        "DATASET_123/PRIVATE/organisation.xml.c4gh",
        "DATASET_123/PRIVATE/rems.xml.c4gh",
        "DATASET_123/PRIVATE/datacite.xml.c4gh",
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

    landing_page_xml = uploaded_by_key["DATASET_123/LANDING_PAGE/landing_page.xml.c4gh"]
    assert "<LANDING_PAGE_SET>" in landing_page_xml
    assert "<REMS_ACCESS_LINK>https://rems.test</REMS_ACCESS_LINK>" in landing_page_xml
    assert "<TAG>doi</TAG>" in landing_page_xml
    assert "<VALUE>https://doi.test</VALUE>" in landing_page_xml


async def test_upload_bp_metadata_xmls_raises_on_upload_error():
    """Upload errors in BP metadata upload helper should fail publish flow."""

    file_provider = S3InboxSDAService(AsyncMock())
    file_provider._add_file_to_bucket = AsyncMock()  # type: ignore[method-assign]

    def get_xml_documents(_submission_id: str, object_type: str | tuple[str, ...]):
        async def _iter():
            if "dataset" in object_type:
                yield "<DATASET/>"

        return _iter()

    services = SimpleNamespace(
        file_provider=file_provider,
        file=SimpleNamespace(is_file_by_path=AsyncMock(return_value=False), add_file=AsyncMock()),
        submission=SimpleNamespace(get_bucket=AsyncMock(return_value="test-bucket")),
        registration=SimpleNamespace(get_registration=AsyncMock(return_value=None)),
        object=SimpleNamespace(get_xml_documents=get_xml_documents),
    )

    file_provider._add_file_to_bucket.side_effect = SystemException("upload failed")  # type: ignore[method-assign]

    with patch("metadata_backend.api.services.bigpicture.XmlProcessor.validate_schema"):
        with pytest.raises(SystemException, match="upload failed"):
            await upload_bp_metadata_xmls(services, "123", "request-user", "oidc-token")

    services.file.add_file.assert_not_awaited()
