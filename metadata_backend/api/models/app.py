"""Application and request state models."""

from typing import Protocol, cast

from fastapi import Request
from starlette.types import ASGIApp

from ...database.postgres.repository import SessionFactory
from .models import User


class AppState(Protocol):
    """Application state for holding session factory."""

    session_factory: SessionFactory


class RequestState(Protocol):
    """Request state for holding authorized user."""

    user: User


def app_state(app: ASGIApp) -> AppState:
    """Get application state."""
    return cast(AppState, app.state)  # type: ignore


def request_state(request: Request) -> RequestState:
    """Get request state."""
    return cast(RequestState, request.state)
