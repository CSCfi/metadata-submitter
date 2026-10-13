"""Test NeIC SDA Admin service."""

import uuid

import httpx
import pytest
import respx
from starlette import status

from metadata_backend.api.exceptions import ServiceHandlerSystemException
from metadata_backend.services.admin_service import USER_FILES_TIMEOUT, AdminServiceHandler

ADMIN_URL = "http://admin.test"
USER_FILES_URL = f"{ADMIN_URL}/users/test_user/files"


@pytest.fixture
def admin_handler(monkeypatch) -> AdminServiceHandler:
    monkeypatch.setenv("ADMIN_URL", ADMIN_URL)
    monkeypatch.setattr("metadata_backend.services.service_handler.RETRY_DELAY", 0)
    return AdminServiceHandler()


def _file(path: str) -> dict[str, str]:
    return {
        "fileID": str(uuid.uuid4()),
        "inboxPath": path,
        "fileStatus": "uploaded",
        "createdAt": "2026-10-12T00:00:00",
    }


def _page(paths: list[str], next_cursor: str | None = None) -> httpx.Response:
    headers = {"X-Next-Cursor": next_cursor} if next_cursor else {}
    return httpx.Response(status.HTTP_200_OK, json=[_file(p) for p in paths], headers=headers)


async def test_get_user_files_follows_cursor(admin_handler):
    """Test that every page is fetched, passing each page's cursor and the path prefix."""
    with respx.mock as mock:
        route = mock.get(USER_FILES_URL).mock(
            side_effect=[
                _page(["DATASET_1/a", "DATASET_1/b"], "cursor-1"),
                _page(["DATASET_1/c", "DATASET_1/d"], "cursor-2"),
                _page(["DATASET_1/e"]),
            ]
        )
        files = await admin_handler.get_user_files("test_user", "1")

    assert [f.inbox_path for f in files] == [f"DATASET_1/{p}" for p in "abcde"]
    assert route.call_count == 3
    params = [dict(call.request.url.params) for call in route.calls]
    assert params == [
        {"path_prefix": "DATASET_1"},
        {"path_prefix": "DATASET_1", "cursor": "cursor-1"},
        {"path_prefix": "DATASET_1", "cursor": "cursor-2"},
    ]
    assert all(call.request.headers["Authorization"] == "Bearer test-admin-token" for call in route.calls)
    assert all(call.request.extensions["timeout"]["read"] == USER_FILES_TIMEOUT for call in route.calls)


async def test_get_user_files_without_dataset(admin_handler):
    """Test that no path prefix is sent without a dataset, on any page."""
    with respx.mock as mock:
        route = mock.get(USER_FILES_URL).mock(side_effect=[_page(["a"], "cursor-1"), _page([])])
        files = await admin_handler.get_user_files("test_user")

    assert [f.inbox_path for f in files] == ["a"]
    assert [dict(call.request.url.params) for call in route.calls] == [{}, {"cursor": "cursor-1"}]


async def test_get_user_files_repeated_cursor(admin_handler):
    """Test that a cursor returned twice is a service error rather than an endless loop."""
    with respx.mock as mock:
        route = mock.get(USER_FILES_URL).mock(
            side_effect=[_page(["a"], "cursor-1"), _page(["b"], "cursor-2"), _page(["c"], "cursor-1")]
        )
        with pytest.raises(ServiceHandlerSystemException):
            await admin_handler.get_user_files("test_user", "1")

    assert route.call_count == 3


async def test_get_user_files_error_on_later_page(admin_handler):
    """Test that a failing later page is a service error rather than a partial list."""
    with respx.mock as mock:
        mock.get(USER_FILES_URL).mock(
            side_effect=[_page(["a"], "cursor-1"), httpx.Response(status.HTTP_400_BAD_REQUEST)]
        )
        with pytest.raises(ServiceHandlerSystemException) as exc_info:
            await admin_handler.get_user_files("test_user", "1")

    assert exc_info.value.service_status_code == status.HTTP_400_BAD_REQUEST
