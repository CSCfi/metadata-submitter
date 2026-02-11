from contextvars import ContextVar
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import Receive, Send

from metadata_backend.api.middlewares import SessionMiddleware
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
