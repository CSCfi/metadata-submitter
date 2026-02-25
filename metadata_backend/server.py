"""Functions to launch backend server."""

import asyncio
import logging
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any, AsyncGenerator, Final, TypeVar, override

import uvicorn
import uvloop
from fastapi import APIRouter, FastAPI, status
from fastapi.encoders import jsonable_encoder
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import ASGIApp

from . import __version__
from .api.errors import register_exception_handlers
from .api.handlers.auth import AuthAPIHandler
from .api.handlers.files import FilesAPIHandler
from .api.handlers.health import HealthAPIHandler
from .api.handlers.key import KeyAPIHandler
from .api.handlers.object import ObjectAPIHandler
from .api.handlers.publish import PublishAPIHandler
from .api.handlers.rems import RemsAPIHandler
from .api.handlers.restapi import RESTAPIServiceHandlers, RESTAPIServices
from .api.handlers.submission import SubmissionAPIHandler
from .api.handlers.user import UserAPIHandler
from .api.middlewares import AuthMiddleware, SessionMiddleware
from .api.models.app import app_state
from .api.models.submission import PaginatedSubmissions
from .api.services.auth import AuthService
from .api.services.file import S3AllasFileProviderService
from .api.services.project import CscProjectService, NbisProjectService, ProjectService
from .conf.conf import (
    API_PREFIX,
    DEPLOYMENT_CSC,
    DEPLOYMENT_NBIS,
)
from .conf.deployment import deployment_config
from .database.postgres.repositories.api_key import ApiKeyRepository
from .database.postgres.repositories.file import FileRepository
from .database.postgres.repositories.object import ObjectRepository
from .database.postgres.repositories.registration import RegistrationRepository
from .database.postgres.repositories.submission import SubmissionRepository
from .database.postgres.repository import (
    _session_context,
    create_engine,
    create_session_factory,
)
from .database.postgres.services.file import FileService
from .database.postgres.services.object import ObjectService
from .database.postgres.services.registration import RegistrationService
from .database.postgres.services.submission import SubmissionService
from .health import DatabaseHealthHandler
from .helpers.logger import LOG
from .services.admin_service import AdminServiceHandler
from .services.auth_service import AuthServiceHandler
from .services.datacite_service import DataciteServiceHandler
from .services.keystone_service import KeystoneServiceHandler
from .services.metax_service import MetaxServiceHandler
from .services.pid_service import PIDServiceHandler
from .services.rems_service import RemsServiceHandler
from .services.ror_service import RorServiceHandler
from .services.service_handler import ServiceHandler

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

ServiceHandlerType = TypeVar("ServiceHandlerType", bound=ServiceHandler)

GET: Final[list[str]] = ["GET"]
POST: Final[list[str]] = ["POST"]
PATCH: Final[list[str]] = ["PATCH"]
HEAD: Final[list[str]] = ["HEAD"]
DELETE: Final[list[str]] = ["DELETE"]


class ExcludeNoneJSONResponse(JSONResponse):
    """Exclude None fields in JSON response."""

    @override
    def render(self, content: Any) -> bytes:
        content = jsonable_encoder(content, exclude_none=True)
        return super().render(content)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    Manages the FastAPI worker lifespan.

    Called once per worker when the FastAPI application starts. Responsible for creating
    and disposing resources that can't be created outside the workers event loop. If
    multiple workers are used then they run in separate OS processes. The database engine
    and connection pool must be created here.
    """

    state = app_state(app)

    # Create database engine.
    engine = await create_engine()

    # Create database session factory.
    state.session_factory = create_session_factory(engine)

    yield

    # Dispose database engine.
    await engine.dispose()

    # CLose health check client.
    await ServiceHandler.close_health_client()


def create_app(session: AsyncSession | None = None) -> ASGIApp:
    """
    Create FastAPI application with all routes, middlewares, and services.

    :param session: AsyncSession used for unit tests.
    """

    config = deployment_config()

    title = f"SD Submit API ({config.DEPLOYMENT})"
    version = __version__
    description = "Please login or provide a JWT or API key bearer token to use the Submission endpoints."

    app = FastAPI(
        title=title,
        version=version,
        description=description,
        lifespan=lifespan,
        default_response_class=ExcludeNoneJSONResponse,
    )

    state = app_state(app)

    # Register exception handlers to format errors as RFC 7807 formatted problem JSON.
    register_exception_handlers(app)

    # Initialise logging.
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
    # logging.getLogger("sqlalchemy.engine").setLevel(logging.DEBUG)
    # logging.getLogger("sqlalchemy.pool").setLevel(logging.DEBUG)

    # Create database repositories.
    submission_repository = SubmissionRepository()
    object_repository = ObjectRepository()
    registration_repository = RegistrationRepository()
    file_repository = FileRepository()
    api_key_repository = ApiKeyRepository()

    # Create database services.
    submission_service = SubmissionService(submission_repository, registration_repository)
    object_service = ObjectService(object_repository)
    registration_service = RegistrationService(registration_repository)
    file_service = FileService(file_repository)
    auth_service = AuthService(api_key_repository)

    # Create project service.
    project_service: ProjectService | None = None

    if config.DEPLOYMENT == DEPLOYMENT_NBIS:
        project_service = NbisProjectService()
    elif config.DEPLOYMENT == DEPLOYMENT_CSC:
        project_service = CscProjectService()

    # Create S3 Allas service.
    file_provider_service = S3AllasFileProviderService()

    # Create service handlers.
    def _create_handler(handler: ServiceHandlerType) -> ServiceHandlerType:
        async def _shutdown() -> None:
            await handler.close()

        app.add_event_handler("shutdown", _shutdown)
        return handler

    metax_handler = None
    ror_handler = None
    datacite_handler = None
    pid_handler = None
    admin_handler = None
    keystone_handler = None

    if config.DEPLOYMENT == DEPLOYMENT_CSC:
        metax_handler = _create_handler(MetaxServiceHandler())
        ror_handler = _create_handler(RorServiceHandler())
        pid_handler = _create_handler(PIDServiceHandler(metax_handler))
        keystone_handler = _create_handler(KeystoneServiceHandler())

    if config.DEPLOYMENT == DEPLOYMENT_NBIS:
        datacite_handler = _create_handler(DataciteServiceHandler(metax_handler))
        admin_handler = _create_handler(AdminServiceHandler())

    rems_handler = _create_handler(RemsServiceHandler())
    auth_handler = _create_handler(AuthServiceHandler())

    # Provide services for FastAPI routes.
    services = RESTAPIServices(
        # Database services.
        submission=submission_service,
        object=object_service,
        registration=registration_service,
        file=file_service,
        # Other services.
        auth=auth_service,
        project=project_service,
        file_provider=file_provider_service,
    )

    # Provide service handlers for FastAPI routes.
    handlers = RESTAPIServiceHandlers(
        datacite=datacite_handler,
        pid=pid_handler,
        metax=metax_handler,
        ror=ror_handler,
        rems=rems_handler,
        keystone=keystone_handler,
        auth=auth_handler,
        admin=admin_handler,
        database=DatabaseHealthHandler(lambda: state.session_factory),
    )

    _object = ObjectAPIHandler(services, handlers)
    _submission = SubmissionAPIHandler(services, handlers)
    _publish_submission = PublishAPIHandler(services, handlers)
    _rems = RemsAPIHandler(services, handlers)
    _file = FilesAPIHandler(services, handlers)
    _health = HealthAPIHandler(services, handlers)
    _key = KeyAPIHandler(services, handlers)
    _user = UserAPIHandler(services, handlers)
    _auth = AuthAPIHandler(auth_handler)

    # API router (authorization required).
    #

    api_router = APIRouter(prefix=API_PREFIX)

    openapi_multipart = {
        "requestBody": {
            "content": {"multipart/form-data": {"schema": {"type": "object"}}},
            "required": True,
        }
    }

    submission_tag: list[str | Enum] = ["Submission"]
    key_tag: list[str | Enum] = ["Key"]
    bucket_tag: list[str | Enum] = ["Bucket"]
    rems_tag: list[str | Enum] = ["Rems"]
    user_tag: list[str | Enum] = ["User"]

    # Submit routes.
    api_router.add_api_route(
        "/submit", _object.add_submission, methods=POST, tags=submission_tag, openapi_extra=openapi_multipart
    )
    api_router.add_api_route(
        "/submit/{submissionId}",
        _object.update_submission,
        methods=PATCH,
        tags=submission_tag,
        openapi_extra=openapi_multipart,
    )
    api_router.add_api_route(
        "/submit/{submissionId}",
        _object.delete_submission,
        methods=DELETE,
        tags=submission_tag,
    )
    api_router.add_api_route(
        "/submit/{submissionId}",
        _object.is_submission,
        methods=HEAD,
        tags=submission_tag,
        summary="Check if submission exists",
    )
    # Submissions routes.
    api_router.add_api_route(
        "/submissions/{submissionId}/objects", _object.list_objects, methods=GET, tags=submission_tag
    )
    api_router.add_api_route(
        "/submissions/{submissionId}/objects/docs", _object.get_objects, methods=GET, tags=submission_tag
    )
    api_router.add_api_route(
        "/submissions",
        _submission.list_submissions,
        methods=GET,
        response_model=PaginatedSubmissions,
        tags=submission_tag,
    )
    api_router.add_api_route(
        "/submissions",
        _submission.create_submission,
        methods=POST,
        status_code=status.HTTP_201_CREATED,
        tags=submission_tag,
    )
    api_router.add_api_route(
        "/submissions/{submissionId}", _submission.get_submission, methods=GET, tags=submission_tag
    )
    api_router.add_api_route(
        "/submissions/{submissionId}/files", _submission.get_submission_files, methods=GET, tags=submission_tag
    )
    api_router.add_api_route(
        "/submissions/{submissionId}/registrations", _submission.get_registrations, methods=GET, tags=submission_tag
    )
    api_router.add_api_route(
        "/submissions/{submissionId}", _submission.update_submission, methods=PATCH, tags=submission_tag
    )  # TODO(improve): consider deprecating endpoint
    api_router.add_api_route(
        "/submissions/{submissionId}",
        _submission.delete_submission,
        methods=DELETE,
        tags=submission_tag,
    )  # TODO(improve): consider deprecating endpoint

    # User routes.
    api_router.add_api_route("/users", _user.get_user, methods=GET, tags=user_tag, summary="Get user information")

    # Publish routes.
    api_router.add_api_route(
        "/publish/{submissionId}", _publish_submission.publish_submission, methods=PATCH, tags=submission_tag
    )

    # Key routes.
    api_router.add_api_route("/api/keys", _key.create_api_key, methods=POST, tags=key_tag)
    api_router.add_api_route("/api/keys", _key.delete_api_key, methods=DELETE, tags=key_tag)
    api_router.add_api_route("/api/keys", _key.get_api_keys, methods=GET, tags=key_tag)

    # File routes.
    api_router.add_api_route("/buckets", _file.get_project_buckets, methods=GET, tags=bucket_tag)
    api_router.add_api_route("/buckets/{bucket}/files", _file.get_files_in_bucket, methods=GET, tags=bucket_tag)
    api_router.add_api_route("/buckets/{bucket}", _file.grant_access_to_bucket, methods=["PUT"], tags=bucket_tag)
    api_router.add_api_route("/buckets/{bucket}", _file.check_bucket_access, methods=HEAD, tags=bucket_tag)

    # REMS routes.
    api_router.add_api_route("/rems", _rems.get_organisations, methods=GET, tags=rems_tag)

    # Auth router (authorization not required).
    #

    auth_router = APIRouter(tags=["Authentication"])
    # TODO(improve): deprecate /aai endpoint
    auth_router.add_api_route(path="/aai", endpoint=_auth.login, methods=GET, include_in_schema=False)
    auth_router.add_api_route(path="/login", endpoint=_auth.login, methods=GET)
    auth_router.add_api_route(path="/callback", endpoint=_auth.callback, methods=GET, include_in_schema=False)
    auth_router.add_api_route(path="/logout", endpoint=_auth.logout, methods=GET)

    # Health router (authorization not required).
    #

    health_router = APIRouter(tags=["Health"])
    health_router.add_api_route("/health", _health.get_health_status, methods=GET)

    # OpenAPI router (authorization not required).
    #

    openapi_router = APIRouter()

    # OpenAPI redirect.
    @openapi_router.get("/", include_in_schema=False)
    async def redirect_to_docs() -> RedirectResponse:
        return RedirectResponse(url="/docs", status_code=status.HTTP_302_FOUND)

    # Add routers.

    app.include_router(api_router)
    app.include_router(auth_router)
    app.include_router(health_router)
    app.include_router(openapi_router)

    LOG.info("FastAPI application initialized with all routes.")

    # Add OIDC security scheme to API router endpoints.

    def custom_openapi() -> dict[str, Any]:
        """Add OIDC security scheme to API router endpoints."""
        if app.openapi_schema:
            # Return cached schema.
            return app.openapi_schema

        # Generate default schema.
        openapi_schema = get_openapi(
            title=title,
            version=version,
            description=description,
            routes=app.routes,
        )

        # Add security scheme.
        openapi_schema["components"]["securitySchemes"] = {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
            }
        }

        # Apply security scheme to API routes.
        for _route in api_router.routes:
            if isinstance(_route, APIRoute):
                path = _route.path
                methods: list[str] = list(_route.methods) or []
                for method in methods:
                    method = method.lower()
                    if path in openapi_schema["paths"] and method in openapi_schema["paths"][path]:
                        openapi_schema["paths"][path][method]["security"] = [{"oidc": []}]

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]

    # ASGI middleware is used to handle authentication and sessions,
    # before any FastAPI/Starlette route is processed.
    asgi_app: ASGIApp = app
    if not session:
        # Create SQLAlchemy sessions with ASGI middleware.
        asgi_app = SessionMiddleware(asgi_app, _session_context)
    # Authenticate users with ASGI middleware.
    asgi_app = AuthMiddleware(asgi_app, auth_service)
    return asgi_app


def main() -> None:
    """Launch the FastAPI server."""
    config = deployment_config()
    host = "0.0.0.0"  # nosec
    port = 5430 if config.DEPLOYMENT == DEPLOYMENT_CSC else 5431

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
