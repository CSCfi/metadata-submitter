from contextvars import ContextVar
from http.cookies import SimpleCookie
from typing import Any, MutableMapping

import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from ..api.errors import problem_response
from ..api.exceptions import AppException, SystemException, UnauthorizedUserException
from ..api.models.models import User
from ..api.services.auth import AuthService
from ..conf.conf import API_PREFIX
from ..helpers.logger import LOG
from .models.app import app_state

AUTH_COOKIE = "access_token"


class SessionMiddleware:
    """
    Assigns database sessions to API requests and puts them in a task- and request-specific
    context variable.

    Starts the database transaction before the request processing begins, and ends it after
    the request processing is completed but before the response is sent back.

    Repositories retrieve the session from the task- and request-specific context variable
    to use the database. The repositories should not begin, commit or rollback the transaction.
    """

    def __init__(self, app: ASGIApp, session_context: ContextVar[AsyncSession]):
        self.app = app
        self.session_context = session_context

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")

        # Only intercept HTTP requests.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
        # Only intercept API requests.
        elif not path.startswith(API_PREFIX):
            await self.app(scope, receive, send)
        else:
            method = scope["method"]

            # Runs before response is processed by the route.
            if self.session_context.get() is not None:
                LOG.error("Session middleware context already set: method: %s, path: %s", method, path)
                raise SystemException("Session context is already set")

            session_factory = app_state(self.app).session_factory

            if session_factory is None:
                raise SystemException("Missing session factory")

            async with session_factory() as session:
                async with session.begin():
                    token = self.session_context.set(session)
                    try:
                        await self.app(scope, receive, send)
                    except Exception as exc:
                        await _send_error_response(scope, receive, send, exc)
                    finally:
                        # Runs before response is returned by the route.
                        self.session_context.reset(token)


class AuthMiddleware:
    """Authenticate API requests."""

    def __init__(self, app: ASGIApp, auth_service: AuthService):
        self.app = app
        self.auth_service = auth_service

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")

        # Only intercept HTTP requests.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
        # Only intercept API requests.
        elif not path.startswith(API_PREFIX):
            await self.app(scope, receive, send)
        else:
            method = scope["method"]

            # Runs before response is processed by the route.

            # Before request is processed by the route.
            LOG.debug("Authenticating request: method: %s, path: %s", method, path)

            try:
                # Extract JWT token or API key.
                jwt_token, api_key = await extract_jwt_token_and_api_key(method, path, scope)

                # Authorize user.
                user = await verify_authorization(method, path, self.auth_service, jwt_token, api_key)

                # Save user in the request state.
                state = scope.setdefault("state", {})
                state["user"] = user

                await self.app(scope, receive, send)
            except Exception as exc:
                await _send_error_response(scope, receive, send, exc)


async def _send_error_response(scope: Scope, receive: Receive, send: Send, exc: Exception) -> None:
    """Send error response for middleware exceptions."""
    request = Request(scope, receive)
    if isinstance(exc, AppException):
        response: Response = problem_response(request, exc.status_code, str(exc))
    else:
        LOG.error("Unexpected middleware exception: %s", exc)
        response = problem_response(request, 500, "Unexpected error")
    await response(scope, receive, send)


async def extract_jwt_token_and_api_key(method: str, path: str, scope: MutableMapping[str, Any]) -> tuple[str, str]:
    headers = Headers(scope=scope)
    cookies = {}
    if headers.get("cookie"):
        c = SimpleCookie()
        c.load(headers.get("cookie"))
        cookies = {k: v.value for k, v in c.items()}

    # Extract JWT token from the Secure HttpOnly cookie.
    jwt_token = cookies.get(AUTH_COOKIE)
    if jwt_token:
        LOG.debug("JWT Authorization token in cookie: method:, %s path: %s", method, path)

    # Extract JWT token or API key from the Authorization header.
    api_key = None
    if not jwt_token:
        auth_header = headers.get("authorization")
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                api_key_or_jwt_token = parts[1]
                try:
                    # Check if token is a JWT
                    jwt.get_unverified_header(api_key_or_jwt_token)
                    jwt_token = api_key_or_jwt_token
                    LOG.debug(
                        "JWT Authorization token in Authorization header: method:, %s path: %s",
                        method,
                        path,
                    )
                except Exception:
                    # Not a JWT -> treat as API key
                    api_key = api_key_or_jwt_token
                    LOG.debug("API key in Authorization header: method:, %s path: %s", method, path)

    return jwt_token, api_key


async def verify_authorization(
    method: str,
    path: str,
    auth_service: AuthService,
    jwt_token: str | None = None,
    api_key: str | None = None,
) -> User:
    """
    Verify the jwt authorization token and returns the authorized user.

    :param method: The HTTP method.
    :param path: The request path.
    :param auth_service: service to validate JWT tokens and API keys.
    :param jwt_token: The JWT token.
    :param api_key: The API key.
    :returns: The authorized user.
    """

    if jwt_token:
        try:
            # Verify the JWT token.
            user_id, user_name = auth_service.validate_jwt_token(jwt_token)
            return User(user_id=user_id, user_name=user_name)
        except Exception:
            LOG.warning("App middleware JWT authorization failed: method:, %s path: %s", method, path)
            raise UnauthorizedUserException("Authorization failed")
    elif api_key:
        try:
            # Verify the API key.
            user_id = await auth_service.validate_api_key(api_key)
            if user_id is None:
                LOG.warning("App middleware API key authorization failed: method:, %s path: %s", method, path)
                raise UnauthorizedUserException("Authorization failed")
            return User(user_id=user_id, user_name=user_id)
        except Exception:
            LOG.warning("App middleware API key authorization failed: method:, %s path: %s", method, path)
            raise UnauthorizedUserException("Authorization failed")
    else:
        raise UnauthorizedUserException("Authorization failed")
