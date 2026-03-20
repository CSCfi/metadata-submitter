"""Tests for Bigpicture API service."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

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
        "landing_page": ["<LANDING_PAGE/>"],
        "organisation": ["<ORGANISATION/>"],
        "rems": ["<REMS/>"],
        BP_SAMPLE_OBJECT_TYPES[0]: ["<BIOLOGICAL_BEING/>"],
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
        submission=SimpleNamespace(get_bucket=AsyncMock(return_value="test-bucket")),
        object=SimpleNamespace(get_xml_documents=get_xml_documents),
    )

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
    }

    assert file_provider._add_file_to_bucket.await_count == len(expected_keys)

    uploaded_keys = {call.kwargs["object_key"] for call in file_provider._add_file_to_bucket.await_args_list}
    assert uploaded_keys == expected_keys


async def test_upload_bp_metadata_xmls_raises_on_upload_error():
    """Upload errors in BP metadata upload helper should fail publish flow."""

    file_provider = S3InboxSDAService(AsyncMock())
    file_provider._add_file_to_bucket = AsyncMock()  # type: ignore[method-assign]

    def get_xml_documents(_submission_id: str, object_type: str | tuple[str, ...]):
        async def _iter():
            if object_type == "dataset":
                yield "<DATASET/>"

        return _iter()

    services = SimpleNamespace(
        file_provider=file_provider,
        submission=SimpleNamespace(get_bucket=AsyncMock(return_value="test-bucket")),
        object=SimpleNamespace(get_xml_documents=get_xml_documents),
    )

    file_provider._add_file_to_bucket.side_effect = SystemException("upload failed")  # type: ignore[method-assign]

    with pytest.raises(SystemException, match="upload failed"):
        await upload_bp_metadata_xmls(services, "123", "request-user", "oidc-token")
