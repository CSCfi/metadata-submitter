from contextvars import ContextVar
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import Receive, Send

from metadata_backend.api.middlewares import AuthMiddleware, SessionMiddleware
from tests.integration.conf import API_PREFIX

mock_session_context: ContextVar[AsyncSession | None] = ContextVar("mock_session_context", default=None)


async def test_session_middleware_api_route(session_factory):
    """Test session middleware for API routes."""
    assert mock_session_context.get() is None

    mock_asgi_app_called = False

    mock_app = MagicMock()
    mock_app.state = SimpleNamespace()
    mock_app.state.session_factory = session_factory

    async def _call(_scope, _receive, _send):
        nonlocal mock_asgi_app_called
        mock_asgi_app_called = True
        session = mock_session_context.get()
        assert session is not None
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1

    mock_app.side_effect = _call

    middleware = SessionMiddleware(mock_app, mock_session_context)

    scope = {
        "type": "http",
        "method": "GET",
        "app": mock_app,
        "path": f"{API_PREFIX}/test",
    }

    await middleware(scope, Mock(spec=Receive), Mock(spec=Send))
    assert mock_asgi_app_called
    assert mock_session_context.get() is None


async def test_session_middleware_non_api_route(session_factory):
    """Test session middleware for non-API routes."""
    mock_asgi_app_called = False

    mock_app = MagicMock()
    mock_app.state = SimpleNamespace()
    mock_app.state.session_factory = session_factory

    async def _call(_scope, _receive, _send):
        nonlocal mock_asgi_app_called
        mock_asgi_app_called = True

    mock_app.side_effect = _call

    middleware = SessionMiddleware(mock_app, mock_session_context)

    scope = {
        "type": "http",
        "method": "GET",
        "app": mock_app,
        "path": "/test",
    }

    await middleware(scope, Mock(spec=Receive), Mock(spec=Send))
    assert mock_asgi_app_called
    assert mock_session_context.get() is None


async def test_session_middleware_sends_response_after_context_reset(session_factory):
    """Test session middleware flushes response after session context reset."""
    mock_app = MagicMock()
    mock_app.state = SimpleNamespace()
    mock_app.state.session_factory = session_factory

    async def _call(_scope, _receive, send):
        assert mock_session_context.get() is not None
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    mock_app.side_effect = _call
    middleware = SessionMiddleware(mock_app, mock_session_context)

    scope = {
        "type": "http",
        "method": "GET",
        "app": mock_app,
        "path": f"{API_PREFIX}/test",
    }

    context_states: list[AsyncSession | None] = []

    async def _send(message):
        context_states.append(mock_session_context.get())

    await middleware(scope, Mock(spec=Receive), _send)
    assert context_states
    assert all(context_state is None for context_state in context_states)


async def test_session_middleware_returns_500_on_app_exception(session_factory):
    """Test session middleware catches app exceptions and sends a 500 response."""
    mock_app = MagicMock()
    mock_app.state = SimpleNamespace()
    mock_app.state.session_factory = session_factory

    async def _call(_scope, _receive, _send):
        raise RuntimeError("boom")

    mock_app.side_effect = _call
    middleware = SessionMiddleware(mock_app, mock_session_context)

    scope = {
        "type": "http",
        "method": "GET",
        "app": mock_app,
        "path": f"{API_PREFIX}/test",
        "headers": [],
        "query_string": b"",
    }

    sent_messages = []

    async def _send(message):
        sent_messages.append(message)

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    await middleware(scope, _receive, _send)

    assert sent_messages
    assert sent_messages[0]["type"] == "http.response.start"
    assert sent_messages[0]["status"] == 500
    assert mock_session_context.get() is None


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
        "path": f"{API_PREFIX}/test",
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
