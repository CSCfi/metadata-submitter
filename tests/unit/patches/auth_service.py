from unittest.mock import AsyncMock, MagicMock


def mock_response(status_code: int, payload: dict | None = None, headers: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    response.json.return_value = payload or {}

    if status_code >= 400:
        response.raise_for_status.side_effect = RuntimeError(f"HTTP {status_code}")
    else:
        response.raise_for_status.return_value = None

    return response


def patch_async_client(monkeypatch, responses: list[MagicMock]) -> MagicMock:
    client = MagicMock()
    client.get = AsyncMock(side_effect=responses)

    async_client_cm = AsyncMock()
    async_client_cm.__aenter__.return_value = client
    async_client_cm.__aexit__.return_value = False

    monkeypatch.setattr(
        "metadata_backend.services.auth_service.httpx.AsyncClient",
        MagicMock(return_value=async_client_cm),
    )

    return client


class MockDPoPHandler:
    def generate_proof(self, htm: str, htu: str, access_token: str | None = None) -> str:
        return "proof"

    def update_nonce(self, nonce: str | None) -> None:
        pass
