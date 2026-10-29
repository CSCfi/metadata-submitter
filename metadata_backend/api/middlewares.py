from contextvars import ContextVar
from http.cookies import SimpleCookie
from typing import Any, Callable, MutableMapping

import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..api.errors import app_exception_response, server_error_response
from ..api.exceptions import AppException, SystemException, UnauthorizedUserException
from ..api.models.models import User
from ..api.services.auth import AuthService
from ..conf.deployment import deployment_config
from ..database.postgres.repository import SessionFactory, session_factory_context
from ..helpers.logger import LOG, AuditState, audit_event, audit_state
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

    def __init__(
        self,
        app: ASGIApp,
        session_context: ContextVar[AsyncSession],
        session_factory_provider: Callable[[], SessionFactory],
    ):
        """
        Initialize the middleware.

        :param app: The wrapped ASGI app.
        :param session_context: The context variable for the request session.
        :param session_factory_provider: Returns the session factory, which is set when the app starts.
        """
        self.app = app
        self.session_context = session_context
        self.session_factory_provider = session_factory_provider
        config = deployment_config()
        # The paths whose requests are wrapped in a database transaction.
        self.transaction_paths = (config.API_PREFIX_V1, config.API_PREFIX_SYNC)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")

        # Only intercept HTTP requests.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
        # Only intercept requests that are given a database transaction.
        elif not path.startswith(self.transaction_paths):
            await self.app(scope, receive, send)
        else:
            method = scope["method"]

            # Runs before response is processed by the route.
            if self.session_context.get() is not None:
                LOG.error("Session middleware context already set: method: %s, path: %s", method, path)
                raise SystemException("Session context is already set")

            session_factory = self.session_factory_provider()
            async with session_factory() as session:
                response_started = False
                # One transaction ended flag per request.
                transaction_ended = False

                async def rollback() -> None:
                    # A transaction that failed to commit may have been closed already, and
                    # rolling back a closed transaction raises.
                    if transaction.is_active:
                        await transaction.rollback()

                async def end_transaction(commit: bool) -> None:
                    """Commit or rollback the transaction, unless it has already ended."""
                    nonlocal transaction_ended
                    if transaction_ended:
                        # Transaction has already ended.
                        return
                    transaction_ended = True
                    if commit:
                        try:
                            await transaction.commit()
                        except Exception:
                            await rollback()
                            raise
                    else:
                        await rollback()

                async def transactional_send(message: Message) -> None:
                    nonlocal response_started

                    # In ASGI, `http.response.start` message ends the status code and headers
                    # to the client. After this response is considered started.
                    # https://asgi.readthedocs.io/en/latest/specs/www.html#response-start-send-event
                    if message["type"] == "http.response.start" and not response_started:
                        # Commit or rollback before sending headers.
                        status = message.get("status", None)
                        commit = status is not None and not 400 <= status < 600
                        LOG.debug(f"{'Commit' if commit else 'Rollback'} session in middleware, status code: {status}")
                        await end_transaction(commit)

                        response_started = True

                    await send(message)

                try:
                    token = self.session_context.set(session)
                    factory_token = session_factory_context.set(session_factory)

                    transaction = await session.begin()

                    await self.app(scope, receive, transactional_send)

                    if not response_started:
                        LOG.error("Unexpected session middleware state (response not started)")
                        await end_transaction(commit=False)

                except Exception as exc:
                    await end_transaction(commit=False)

                    if not response_started:
                        await _send_error_response(scope, receive, send, exc)
                    else:
                        # Response has started, we can't send an error response anymore.
                        raise

                finally:
                    session_factory_context.reset(factory_token)
                    self.session_context.reset(token)


class AuthMiddleware:
    """Authenticate API requests."""

    def __init__(self, app: ASGIApp, auth_service: AuthService):
        self.app = app
        self.auth_service = auth_service
        self.api_prefix_v1 = deployment_config().API_PREFIX_V1

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")

        # Only intercept HTTP requests.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
        # Only intercept API requests.
        elif not path.startswith(self.api_prefix_v1):
            await self.app(scope, receive, send)
        else:
            method = scope["method"]

            # Runs before response is processed by the route.

            # Before request is processed by the route.
            LOG.debug("Authenticating request: method: %s, path: %s", method, path)

            response_started = False

            async def tracking_send(message: Message) -> None:
                nonlocal response_started
                await send(message)
                # The response has started only once its start has been sent.
                if message["type"] == "http.response.start":
                    response_started = True

            try:
                # Extract JWT token or API key.
                jwt_token, api_key = await extract_jwt_token_and_api_key(method, path, scope)

                # Authorize user.
                user = await verify_authorization(method, path, self.auth_service, jwt_token, api_key)

                # Save user in the request state.
                state = scope.setdefault("state", {})
                state["user"] = user

                # Save user for the audit records of the request.
                audit = audit_state.get()
                if audit is not None:
                    audit.user_id = user.user_id

                await self.app(scope, receive, tracking_send)
            except Exception as exc:
                if response_started:
                    # A response, such as the generic error one, has already been sent and cannot be replaced.
                    LOG.exception("Exception after the response started: method: %s, path: %s", method, path)
                else:
                    await _send_error_response(scope, receive, send, exc)


class AuditMiddleware:
    """
    Write an audit record of every API request.

    This is the outermost middleware, so that the record has the status the client received.
    It sets the audit_state context variable for the request, and the authentication middleware
    sets the state's user once the user is authenticated, so that the record has the user.
    """

    def __init__(self, app: ASGIApp):
        self.app = app
        self.api_prefix_v1 = deployment_config().API_PREFIX_V1

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")

        # Only intercept HTTP requests.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
        # Only intercept API requests.
        elif not path.startswith(self.api_prefix_v1):
            await self.app(scope, receive, send)
        else:
            token = audit_state.set(AuditState())
            status: int | None = None

            async def audit_send(message: Message) -> None:
                nonlocal status
                if message["type"] == "http.response.start":
                    status = message["status"]
                await send(message)

            try:
                await self.app(scope, receive, audit_send)
            finally:
                audit_event(
                    "http.request",
                    f"{scope['method']} {path} {status if status is not None else 'no response'}",
                    method=scope["method"],
                    path=path,
                    route=getattr(scope.get("route"), "path", None),
                    status=status,
                )
                audit_state.reset(token)


def add_middlewares(app: ASGIApp, auth_service: AuthService, session_context: ContextVar[AsyncSession]) -> ASGIApp:
    """
    Wrap the app with the audit, session and authentication middleware.

    The audit middleware is the outermost one, so that it records the status the client received.
    The session middleware wraps the authentication middleware, so that the database session is
    available when the authentication middleware validates an API key.

    :param app: The FastAPI app.
    :param auth_service: The service to validate JWT tokens and API keys.
    :param session_context: The context variable for the request session.
    :returns: The wrapped app.
    """
    auth_middleware = AuthMiddleware(app, auth_service)
    session_middleware = SessionMiddleware(auth_middleware, session_context, lambda: app_state(app).session_factory)
    return AuditMiddleware(session_middleware)


async def _send_error_response(scope: Scope, receive: Receive, send: Send, exc: Exception) -> None:
    """Send error response for middleware exceptions."""
    request = Request(scope, receive)
    if isinstance(exc, AppException):
        response: Response = app_exception_response(request, exc)
    else:
        # With the traceback, since the exception is not raised further for the server to log.
        LOG.error("Unexpected middleware exception: %s", exc, exc_info=exc)
        response = server_error_response(request, 500, "Unexpected error")
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
        LOG.debug("JWT Authorization token in cookie: method: %s, path: %s", method, path)

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
                        "JWT Authorization token in Authorization header: method: %s, path: %s",
                        method,
                        path,
                    )
                except Exception:
                    # Not a JWT -> treat as API key
                    api_key = api_key_or_jwt_token
                    LOG.debug("API key in Authorization header: method: %s, path: %s", method, path)

    return jwt_token, api_key


async def verify_authorization(
    method: str,
    path: str,
    auth_service: AuthService,
    jwt_token: str | None = None,
    api_key: str | None = None,
) -> User:
    """Verify the jwt authorization token and returns the authorized user.

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
        except Exception as exc:
            LOG.warning("App middleware JWT authorization failed: method: %s, path: %s, error: %s", method, path, exc)
            raise UnauthorizedUserException("Authorization failed")
    elif api_key:
        try:
            # Verify the API key.
            user_id = await auth_service.validate_api_key(api_key)
            if user_id is None:
                LOG.warning("App middleware API key authorization failed: method: %s, path: %s", method, path)
                raise UnauthorizedUserException("Authorization failed")
            return User(user_id=user_id, user_name=user_id)
        except Exception as exc:
            LOG.warning(
                "App middleware API key authorization failed: method: %s, path: %s, error: %s", method, path, exc
            )
            raise UnauthorizedUserException("Authorization failed")
    else:
        raise UnauthorizedUserException("Authorization failed")
