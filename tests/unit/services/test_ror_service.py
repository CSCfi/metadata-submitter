from unittest.mock import AsyncMock

import pytest
from aiocache import caches

from metadata_backend.services.ror_service import RorServiceHandler


@pytest.fixture(autouse=True)
async def clear_cache():
    await caches.get("default").clear()


async def test_is_ror_organisation_found():
    handler = RorServiceHandler()

    mock_response = {
        "items": [
            {
                "id": "http://www.yso.fi/onto/okm-organisaatio/1",
                "names": [
                    {"value": "University of Helsinki", "types": ["ror_display"]},
                    {"value": "Helsingin yliopisto", "types": ["alias"]},
                ],
            }
        ]
    }

    handler._request = AsyncMock(return_value=mock_response)

    result = await handler.get_organisation("University of Helsinki")
    assert result == ("http://www.yso.fi/onto/okm-organisaatio/1", "University of Helsinki")
    handler._request.assert_called_once_with(
        method="GET", path="/organizations", params={"query": '"University of Helsinki"'}
    )


async def test_is_ror_organisation_multiple_found():
    handler = RorServiceHandler()

    mock_response = {
        "items": [
            {
                "id": "http://www.yso.fi/onto/okm-organisaatio/1",
                "names": [{"value": "University A", "types": ["ror_display"]}],
            },
            {
                "id": "http://www.yso.fi/onto/okm-organisaatio/2",
                "names": [{"value": "University B", "types": ["ror_display"]}],
            },
        ]
    }

    handler._request = AsyncMock(return_value=mock_response)

    result = await handler.get_organisation("University")
    assert result is None


async def test_is_ror_organisation_not_found():
    handler = RorServiceHandler()

    mock_response = {"items": []}
    handler._request = AsyncMock(return_value=mock_response)

    result = await handler.get_organisation("Nonexistent University")
    assert result is None
