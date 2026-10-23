"""Integration tests for the NeIC SDA Admin service against the mock Admin API."""

import uuid

import pytest

from metadata_backend.services.admin_service import AdminServiceHandler
from tests.integration.conf import mock_user
from tests.integration.helpers import _mock_admin_headers, _mock_admin_url, add_mock_admin_files


@pytest.fixture
async def admin_handler(monkeypatch):
    monkeypatch.setenv("ADMIN_URL", _mock_admin_url())
    # The mock's admin token if configured, otherwise a token for a user the mock treats as an admin.
    monkeypatch.setenv("ADMIN_TOKEN", _mock_admin_headers(mock_user)["Authorization"].removeprefix("Bearer "))
    handler = AdminServiceHandler()
    yield handler
    await handler.close()


async def test_get_user_files_all_pages(monkeypatch, admin_handler):
    """Test that a user's files spanning several pages of the mock are all returned, and no other dataset's."""
    dataset_id = uuid.uuid4().hex
    paths = {f"DATASET_{dataset_id}/IMAGES/image_{i}.dcm.c4gh" for i in range(5)}
    await add_mock_admin_files(mock_user, paths | {f"DATASET_other_{dataset_id}/image.dcm.c4gh"})

    requests = 0
    send = admin_handler._send

    async def _send(**kwargs):
        nonlocal requests
        requests += 1
        return await send(**kwargs)

    monkeypatch.setattr(admin_handler, "_send", _send)
    files = await admin_handler.get_user_files(mock_user, f"DATASET_{dataset_id}")

    assert sorted(f.inbox_path for f in files) == sorted(paths)
    # Otherwise the mock returned every file at once, and nothing above followed a cursor.
    assert requests > 1
