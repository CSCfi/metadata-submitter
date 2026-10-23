"""Test NeIC SDA Admin service."""

import json
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
        files = await admin_handler.get_user_files("test_user", "DATASET_1")

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
            side_effect=[
                _page(["a"], "cursor-1"),
                _page(["b"], "cursor-2"),
                _page(["c"], "cursor-1"),
                _page(["d"]),
            ]
        )
        with pytest.raises(ServiceHandlerSystemException):
            await admin_handler.get_user_files("test_user", "DATASET_1")

    assert route.call_count == 3


async def test_get_user_files_error_on_later_page(admin_handler):
    """Test that a failing later page is a service error rather than a partial list."""
    with respx.mock as mock:
        mock.get(USER_FILES_URL).mock(
            side_effect=[_page(["a"], "cursor-1"), httpx.Response(status.HTTP_400_BAD_REQUEST)]
        )
        with pytest.raises(ServiceHandlerSystemException) as exc_info:
            await admin_handler.get_user_files("test_user", "DATASET_1")

    assert exc_info.value.service_status_code == status.HTTP_400_BAD_REQUEST


DATASET_FILES_URL = f"{ADMIN_URL}/dataset/d1/files"


def _dataset_page(accession_ids: list[str], next_cursor: str | None = None) -> httpx.Response:
    headers = {"X-Next-Cursor": next_cursor} if next_cursor else {}
    files = [
        {
            "id": str(uuid.uuid4()),
            "accessionID": accession_id,
            "path": f"DATASET_d1/{accession_id}.c4gh",
            "createdAt": "2026-10-12T00:00:00Z",
            "size": 20,
            "decryptedSize": 10,
            "checksums": [{"type": "sha256", "checksum": "abc"}],
        }
        for accession_id in accession_ids
    ]
    return httpx.Response(status.HTTP_200_OK, json=files, headers=headers)


async def test_list_ingested_files_follows_cursor(admin_handler):
    """Test that every page of the dataset files is fetched."""
    with respx.mock as mock:
        route = mock.get(DATASET_FILES_URL).mock(
            side_effect=[_dataset_page(["a", "b"], "cursor-1"), _dataset_page(["c"])]
        )
        files = await admin_handler.list_ingested_files("d1")

    assert [f.accession_id for f in files] == ["a", "b", "c"]
    assert [dict(call.request.url.params) for call in route.calls] == [
        {},
        {"cursor": "cursor-1"},
    ]


async def test_list_ingested_files_repeated_cursor(admin_handler):
    """Test that a cursor returned twice is a service error rather than an endless loop."""
    with respx.mock as mock:
        route = mock.get(DATASET_FILES_URL).mock(
            side_effect=[_dataset_page(["a"], "cursor-1"), _dataset_page(["b"], "cursor-1"), _dataset_page(["c"])]
        )
        with pytest.raises(ServiceHandlerSystemException):
            await admin_handler.list_ingested_files("d1")

    assert route.call_count == 2


async def test_list_ingested_files_unknown_dataset(admin_handler):
    """Test that an unknown dataset is None rather than an error."""
    with respx.mock as mock:
        mock.get(DATASET_FILES_URL).mock(return_value=httpx.Response(status.HTTP_404_NOT_FOUND))
        assert await admin_handler.list_ingested_files("d1") is None


async def test_remove_ingested_file(admin_handler):
    """Test that a file removal is requested for the dataset and accession."""
    with respx.mock as mock:
        route = mock.delete(f"{ADMIN_URL}/dataset/d1/files/f1").mock(
            return_value=httpx.Response(status.HTTP_202_ACCEPTED)
        )
        await admin_handler.remove_ingested_file("d1", "f1")

    assert route.call_count == 1
    assert route.calls[0].request.headers["Authorization"] == "Bearer test-admin-token"


async def test_mark_file_removed(admin_handler):
    """Test that a removed event is logged for the file, with the reason."""
    with respx.mock as mock:
        route = mock.post(f"{ADMIN_URL}/file/events/f1/removed").mock(return_value=httpx.Response(status.HTTP_200_OK))
        await admin_handler.mark_file_removed("f1", "replaced")

    assert route.call_count == 1
    assert route.calls[0].request.headers["Authorization"] == "Bearer test-admin-token"
    assert json.loads(route.calls[0].request.content) == {"reason": "replaced"}
