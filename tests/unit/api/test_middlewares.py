import json
from contextvars import ContextVar
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import Receive, Send

from metadata_backend.api.middlewares import AuditMiddleware, AuthMiddleware, SessionMiddleware, add_middlewares
from metadata_backend.conf.deployment import deployment_config
from metadata_backend.database.postgres.repository import create_engine, create_session_factory, get_sqllite_db_url
from tests.unit.patches.user import MOCK_USER_ID, patch_verify_authorization

mock_session_context: ContextVar[AsyncSession | None] = ContextVar("mock_session_context", default=None)


_AUDITED_TEST_ROUTE = "/items/{item_id}"


async def test_session_middleware_api_route(session_factory):
    """Test session middleware for API routes."""
    assert mock_session_context.get() is None

    mock_asgi_app_called = False

    mock_app = MagicMock()

    async def _call(_scope, _receive, _send):
        nonlocal mock_asgi_app_called
        mock_asgi_app_called = True
        session = mock_session_context.get()
        assert session is not None
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1

    mock_app.side_effect = _call

    middleware = SessionMiddleware(mock_app, mock_session_context, lambda: session_factory)

    scope = {
        "type": "http",
        "method": "GET",
        "app": mock_app,
        "path": f"{deployment_config().API_PREFIX_V1}/test",
    }

    await middleware(scope, Mock(spec=Receive), Mock(spec=Send))
    assert mock_asgi_app_called
    assert mock_session_context.get() is None


async def test_session_middleware_non_api_route(session_factory):
    """Test session middleware for non-API routes."""
    mock_asgi_app_called = False

    mock_app = MagicMock()

    async def _call(_scope, _receive, _send):
        nonlocal mock_asgi_app_called
        mock_asgi_app_called = True

    mock_app.side_effect = _call

    middleware = SessionMiddleware(mock_app, mock_session_context, lambda: session_factory)

    scope = {
        "type": "http",
        "method": "GET",
        "app": mock_app,
        "path": "/test",
    }

    await middleware(scope, Mock(spec=Receive), Mock(spec=Send))
    assert mock_asgi_app_called
    assert mock_session_context.get() is None


async def test_session_middleware_set_and_reset_context(session_factory):
    """Test that session middleware sets and resets the session context."""
    mock_app = MagicMock()

    assert mock_session_context.get() is None, "Session not reset before request"

    async def _call(_scope, _receive, send):
        assert mock_session_context.get() is not None, "Session not available during request"
        await send({"type": "http.response.start", "status": 200, "headers": []})
        # Test with streaming response.
        await send({"type": "http.response.body", "body": b"ok", "more_body": True})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    mock_app.side_effect = _call
    middleware = SessionMiddleware(mock_app, mock_session_context, lambda: session_factory)

    scope = {
        "type": "http",
        "method": "GET",
        "app": mock_app,
        "path": f"{deployment_config().API_PREFIX_V1}/test",
    }

    sent_messages = []

    async def _send(_message):
        sent_messages.append(_message)
        assert mock_session_context.get() is not None, "Session not available during request"

    await middleware(scope, Mock(spec=Receive), _send)

    assert sent_messages == [
        {"headers": [], "status": 200, "type": "http.response.start"},
        {"body": b"ok", "more_body": True, "type": "http.response.body"},
        {"body": b"ok", "more_body": False, "type": "http.response.body"},
    ]

    assert mock_session_context.get() is None, "Session not reset after request"


async def test_session_middleware_returns_problem_json_on_exception(session_factory):
    """Test session middleware catches exceptions and returns problem json with 500 response."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    mock_app = MagicMock()

    async def _call(_scope, _receive, _send):
        raise RuntimeError("boom")

    mock_app.side_effect = _call
    middleware = SessionMiddleware(mock_app, mock_session_context, lambda: session_factory)

    scope = {
        "type": "http",
        "method": "GET",
        "app": mock_app,
        "path": f"{api_prefix_v1}/test",
        "headers": [],
        "query_string": b"",
    }

    sent_messages = []

    async def _send(message):
        sent_messages.append(message)

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    await middleware(scope, _receive, _send)

    assert sent_messages == [
        {
            "headers": [
                (b"content-type", b"application/problem+json"),
                (b"content-length", sent_messages[0]["headers"][1][1]),
            ],
            "status": 500,
            "type": "http.response.start",
        },
        {
            "body": b'{"type":"about:blank","title":"Internal Server Error","detail":"'
            b'Unexpected error","status":500,"instance":"' + api_prefix_v1.encode() + b'/test"}',
            "type": "http.response.body",
        },
    ]

    assert mock_session_context.get() is None, "Session not reset after request"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code, expected_action",
    [
        (200, "commit"),
        (201, "commit"),
        (302, "commit"),
        (400, "rollback"),
        (404, "rollback"),
        (500, "rollback"),
        (None, "rollback"),  # missing status
    ],
)
async def test_session_middleware_commit_and_rollback(status_code, expected_action):
    """Check that session middleware commits or rollbacks based on HTTP status."""

    mock_transaction = AsyncMock()
    mock_session = AsyncMock()
    mock_session.begin = AsyncMock(return_value=mock_transaction)

    _mock_session_factory = AsyncMock()
    _mock_session_factory.__aenter__.return_value = mock_session
    _mock_session_factory.__aexit__.return_value = None

    # session_factory must be a *normal function*
    def mock_session_factory():
        return _mock_session_factory

    mock_app = MagicMock()

    async def _call(_scope, _receive, _send):
        await _send({"type": "http.response.start", "status": status_code, "headers": []})
        await _send({"type": "http.response.body", "body": b"ok", "more_body": False})

    mock_app.side_effect = _call

    middleware = SessionMiddleware(mock_app, mock_session_context, lambda: mock_session_factory)

    scope = {
        "type": "http",
        "method": "GET",
        "app": mock_app,
        "path": f"{deployment_config().API_PREFIX_V1}/test",
    }

    sent_messages = []

    async def _send(_message):
        sent_messages.append(_message)

    await middleware(scope, Mock(spec=Receive), _send)

    if expected_action == "commit":
        mock_transaction.commit.assert_awaited_once()
        mock_transaction.rollback.assert_not_awaited()
    else:
        mock_transaction.rollback.assert_awaited_once()
        mock_transaction.commit.assert_not_awaited()


async def test_auth_middleware_missing_authorization_returns_401():
    """Test auth middleware returns 401 when authorization is missing."""
    mock_asgi_app_called = False

    mock_app = MagicMock()

    async def _call(_scope, _receive, _send):
        nonlocal mock_asgi_app_called
        mock_asgi_app_called = True

    mock_app.side_effect = _call

    auth_service = MagicMock()
    middleware = AuthMiddleware(mock_app, auth_service)

    scope = {
        "type": "http",
        "method": "GET",
        "path": f"{deployment_config().API_PREFIX_V1}/test",
        "headers": [],
    }

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    sent_messages = []

    async def _send(message):
        sent_messages.append(message)

    await middleware(scope, _receive, _send)

    assert not mock_asgi_app_called
    assert sent_messages
    assert sent_messages[0]["type"] == "http.response.start"
    assert sent_messages[0]["status"] == 401
    assert json.loads(sent_messages[1]["body"]) == {
        "type": "about:blank",
        "title": "Unauthorized",
        "detail": "User error",
        "status": 401,
        "instance": f"{deployment_config().API_PREFIX_V1}/test",
        "errors": ["Authorization failed"],
    }


async def test_auth_middleware_does_not_replace_started_response(monkeypatch):
    """Test auth middleware sends no second response for an error raised after the response started.

    Starlette sends the generic error response for an unexpected exception and then re-raises it.
    """

    async def _call(_scope, _receive, send):
        await send({"type": "http.response.start", "status": 500, "headers": []})
        await send({"type": "http.response.body", "body": b"generic"})
        raise RuntimeError("secret detail")

    mock_app = MagicMock(side_effect=_call)
    monkeypatch.setattr("metadata_backend.api.middlewares.verify_authorization", AsyncMock(return_value=Mock()))
    middleware = AuthMiddleware(mock_app, MagicMock())

    scope = {
        "type": "http",
        "method": "GET",
        "path": f"{deployment_config().API_PREFIX_V1}/test",
        "headers": [],
    }

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    sent_messages = []

    async def _send(message):
        sent_messages.append(message)

    await middleware(scope, _receive, _send)

    assert [m["type"] for m in sent_messages] == ["http.response.start", "http.response.body"]
    assert sent_messages[1]["body"] == b"generic"


async def test_add_middlewares_api_key_has_session(session_factory):
    """Test that the session is available when the auth middleware validates an API key."""
    session_context: ContextVar[AsyncSession | None] = ContextVar("api_key_session_context", default=None)

    auth_service = MagicMock()
    # The API key is valid only if the session is available when it is validated.
    auth_service.validate_api_key = AsyncMock(side_effect=lambda _api_key: session_context.get() and "user")
    mock_app = AsyncMock()
    mock_app.state = SimpleNamespace(session_factory=session_factory)

    scope = {
        "type": "http",
        "method": "GET",
        "path": f"{deployment_config().API_PREFIX_V1}/test",
        "headers": [(b"authorization", b"Bearer keyid.secret")],
    }
    await add_middlewares(mock_app, auth_service, session_context)(scope, AsyncMock(), AsyncMock())

    auth_service.validate_api_key.assert_awaited_once_with("keyid.secret")
    # The request reaches the app only if the API key was valid.
    mock_app.assert_awaited_once()


@pytest.fixture
def audited_client() -> TestClient:
    """Create a client of an app with two API routes, wrapped in the audit and authentication middleware."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    app = FastAPI()

    @app.get(f"{api_prefix_v1}{_AUDITED_TEST_ROUTE}")
    async def get_item(item_id: str) -> dict:
        return {"item_id": item_id}

    @app.get(f"{api_prefix_v1}/fail")
    async def fail() -> dict:
        raise RuntimeError("unexpected")

    return TestClient(AuditMiddleware(AuthMiddleware(app, MagicMock())), raise_server_exceptions=False)


def test_audit_middleware_authenticated_request(audited_client, audit_records):
    """Test that an authenticated request is audited with the user and the route."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    path = f"{api_prefix_v1}/items/item1"

    with patch_verify_authorization:
        response = audited_client.get(f"{path}?q=secret-query", headers={"Authorization": "Bearer secret-api-key"})

    assert response.status_code == 200
    [record] = audit_records()
    del record["time"]
    # The record has these fields only, so neither the client address, the credentials nor the
    # query are logged.
    assert record == {
        "levelname": "AUDIT",
        "action": "http.request",
        "message": f"GET {path} 200",
        "user_id": MOCK_USER_ID,
        "method": "GET",
        "path": path,
        "route": f"{api_prefix_v1}{_AUDITED_TEST_ROUTE}",
        "status": 200,
    }


def test_audit_middleware_unauthenticated_request(audited_client, audit_records):
    """Test that a request that fails authentication is audited without a user."""
    path = f"{deployment_config().API_PREFIX_V1}/items/item1"

    response = audited_client.get(path)

    assert response.status_code == 401
    [record] = audit_records()
    del record["time"]
    assert record == {
        "levelname": "AUDIT",
        "action": "http.request",
        "message": f"GET {path} 401",
        "user_id": None,
        "method": "GET",
        "path": path,
        # The request did not reach a route.
        "route": None,
        "status": 401,
    }


def test_audit_middleware_unexpected_error(audited_client, audit_records):
    """Test that a request that fails with an unexpected error is audited with the status 500."""
    path = f"{deployment_config().API_PREFIX_V1}/fail"

    with patch_verify_authorization:
        response = audited_client.get(path)

    assert response.status_code == 500
    [record] = audit_records()
    del record["time"]
    assert record == {
        "levelname": "AUDIT",
        "action": "http.request",
        "message": f"GET {path} 500",
        "user_id": MOCK_USER_ID,
        "method": "GET",
        "path": path,
        "route": path,
        "status": 500,
    }


async def test_audit_middleware_exception_before_response(audit_records):
    """Test that an exception raised before the response started is audited without a status."""
    path = f"{deployment_config().API_PREFIX_V1}/test"
    mock_app = AsyncMock(side_effect=RuntimeError("unexpected"))
    scope = {"type": "http", "method": "POST", "path": path}

    with pytest.raises(RuntimeError):
        await AuditMiddleware(mock_app)(scope, AsyncMock(), AsyncMock())

    [record] = audit_records()
    del record["time"]
    assert record == {
        "levelname": "AUDIT",
        "action": "http.request",
        "message": f"POST {path} no response",
        "user_id": None,
        "method": "POST",
        "path": path,
        "route": None,
        "status": None,
    }


async def test_audit_middleware_ignores_other_paths(audit_records):
    """Test that requests outside the API are not audited."""
    mock_app = AsyncMock()

    await AuditMiddleware(mock_app)({"type": "http", "method": "GET", "path": "/health"}, AsyncMock(), AsyncMock())

    mock_app.assert_awaited_once()
    assert audit_records() == []


async def test_add_middlewares_commit_failure(tmp_path, audit_records, caplog):
    """Test that the client receives an error response if the transaction cannot be committed.

    The commit fails when the route's response starts, so the route's response is never sent.
    A real session is used, so that the test fails if the middleware rolls back the transaction
    again after the failed commit has closed it.
    """
    engine = await create_engine(get_sqllite_db_url(str(tmp_path / "commit.db")))

    @event.listens_for(engine.sync_engine, "commit")
    def fail_commit(_connection) -> None:
        raise RuntimeError("commit failed")

    app = FastAPI()
    app.state.session_factory = create_session_factory(engine)
    path = f"{deployment_config().API_PREFIX_V1}/items"

    @app.post(path)
    async def create_item() -> dict:
        await mock_session_context.get().execute(text("SELECT 1"))
        return {"created": True}

    client = TestClient(add_middlewares(app, MagicMock(), mock_session_context), raise_server_exceptions=False)

    try:
        with patch_verify_authorization:
            response = client.post(path)
    finally:
        await engine.dispose()

    # The app's error response, not the server's plain text one.
    assert response.json() == {
        "type": "about:blank",
        "title": "Internal Server Error",
        "detail": "Unexpected error",
        "status": 500,
        "instance": path,
    }
    # The failure is logged with its traceback.
    [log_record] = [r for r in caplog.records if r.getMessage() == "Unexpected middleware exception: commit failed"]
    assert log_record.exc_info is not None
    [record] = audit_records()
    del record["time"]
    assert record == {
        "levelname": "AUDIT",
        "action": "http.request",
        "message": f"POST {path} 500",
        "user_id": MOCK_USER_ID,
        "method": "POST",
        "path": path,
        "route": path,
        "status": 500,
    }
