"""Functions to launch backend server."""

import asyncio
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any, AsyncGenerator, Final, override

import uvicorn
from fastapi import APIRouter, Depends, FastAPI, status
from fastapi.encoders import jsonable_encoder
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response
from starlette.types import ASGIApp

from . import __version__
from .api.dependencies import verify_sync
from .api.errors import ERRORS_DESCRIPTION, add_error_responses, register_exception_handlers
from .api.handlers.auth import AuthAPIHandler
from .api.handlers.files import FilesAPIHandler
from .api.handlers.health import HealthAPIHandler
from .api.handlers.key import KeyAPIHandler
from .api.handlers.object import ObjectAPIHandler
from .api.handlers.publish import PublishAPIHandler
from .api.handlers.rems import RemsAPIHandler
from .api.handlers.restapi import RESTAPIServiceHandlers, RESTAPIServices
from .api.handlers.submission import SubmissionAPIHandler
from .api.handlers.sync import SyncAPIHandler
from .api.handlers.user import UserAPIHandler
from .api.middlewares import AuditMiddleware, AuthMiddleware, add_middlewares
from .api.models.app import app_state
from .api.models.submission import PaginatedSubmissions
from .api.services.auth import AuthService
from .api.services.ingest import SDAIngestService
from .api.services.openbao import OpenBaoService
from .conf.database import database_config
from .conf.deployment import deployment_config
from .conf.openbao import openbao_config
from .conf.sync import sync_config
from .database.postgres.repositories.api_key import ApiKeyRepository
from .database.postgres.repositories.dispatch import DispatchRepository
from .database.postgres.repositories.file import FileRepository
from .database.postgres.repositories.object import ObjectRepository
from .database.postgres.repositories.registration import RegistrationRepository
from .database.postgres.repositories.submission import SubmissionRepository
from .database.postgres.repository import (
    _session_context,
    create_engine,
    create_session_factory,
    migrate_schema,
)
from .database.postgres.services.dispatch import DispatchService
from .database.postgres.services.file import FileService
from .database.postgres.services.object import ObjectService
from .database.postgres.services.registration import RegistrationService
from .database.postgres.services.submission import SubmissionService
from .deployment import ServiceHandlerType, deployment_profile
from .health import DatabaseHealthHandler
from .helpers.logger import LOG
from .services.rems_service import RemsServiceHandler
from .services.service_handler import ServiceHandler

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

    # Create encryption service.
    openbao_service = getattr(state, "openbao_service", None)
    if openbao_service is not None:
        # Check encryption service at startup.
        await openbao_service.validate()

    # Start background ingest scanner task for NBIS deployment.
    ingest_scanner_task: asyncio.Task[None] | None = None
    ingest_scanner_service = getattr(state, "ingest_scanner_service", None)
    if ingest_scanner_service is not None:
        LOG.info("Starting background ingest scanner task")
        ingest_scanner_task = asyncio.create_task(ingest_scanner_service.run_forever())

    LOG.info("Server started")

    yield

    LOG.info("Server stopping")

    if ingest_scanner_task is not None:
        ingest_scanner_task.cancel()
        try:
            await ingest_scanner_task
        except asyncio.CancelledError:
            pass

    if openbao_service is not None:
        await openbao_service.close()

    # Dispose database engine.
    await engine.dispose()

    # CLose health check client.
    await ServiceHandler.close_health_client()

    LOG.info("Server stopped")


def create_app(session: AsyncSession | None = None) -> ASGIApp:
    """
    Create FastAPI application with all routes, middlewares, and services.

    :param session: AsyncSession used for unit tests.
    """

    config = deployment_config()
    profile = deployment_profile()

    title = f"SD Submit API ({config.DEPLOYMENT})"
    version = __version__
    description = (
        "Please login or provide a JWT or API key bearer token to use the Submission endpoints.\n" + ERRORS_DESCRIPTION
    )

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

    # Create the encryption service.
    openbao_service = OpenBaoService() if openbao_config().OPENBAO_URL else None
    app.state.openbao_service = openbao_service

    # Create database repositories.
    submission_repository = SubmissionRepository()
    object_repository = ObjectRepository()
    registration_repository = RegistrationRepository()
    file_repository = FileRepository()
    api_key_repository = ApiKeyRepository()
    dispatch_repository = DispatchRepository()

    # Create database services.
    submission_service = SubmissionService(submission_repository, registration_repository)
    object_service = ObjectService(object_repository, openbao_service)
    registration_service = RegistrationService(registration_repository)
    file_service = FileService(file_repository)
    auth_service = AuthService(api_key_repository)
    dispatch_service = DispatchService(dispatch_repository)

    # Create service handlers.
    def _create_handler(handler: ServiceHandlerType) -> ServiceHandlerType:
        async def _shutdown() -> None:
            await handler.close()

        app.router.add_event_handler("shutdown", _shutdown)
        return handler

    # Create deployment-specific services and service handlers.
    deployment_services = profile.create_services(_create_handler, object_service, file_service)

    rems_handler = _create_handler(RemsServiceHandler())

    # Provide services for FastAPI routes.
    services = RESTAPIServices(
        # Database services.
        submission=submission_service,
        object=object_service,
        registration=registration_service,
        file=file_service,
        dispatch=dispatch_service,
        # Other services.
        auth=auth_service,
        project=deployment_services.project,
        file_provider=deployment_services.file_provider,
        license_provider=deployment_services.license_provider,
    )

    # Provide service handlers for FastAPI routes.
    handlers = RESTAPIServiceHandlers(
        datacite=deployment_services.datacite,
        pid=deployment_services.pid,
        metax=deployment_services.metax,
        ror=deployment_services.ror,
        rems=rems_handler,
        keystone=deployment_services.keystone,
        auth=deployment_services.auth,
        admin=deployment_services.admin,
        database=DatabaseHealthHandler(lambda: state.session_factory),
        openbao=openbao_service,
    )

    # Provide ingest scanner service.
    app.state.ingest_scanner_service = None
    if profile.sda_ingest and deployment_services.admin is not None and not session:
        app.state.ingest_scanner_service = SDAIngestService(
            services,
            handlers,
            session_factory_provider=lambda: app_state(app).session_factory,
        )

    _object = ObjectAPIHandler(services, handlers)
    _submission = SubmissionAPIHandler(services, handlers)
    _publish_submission = PublishAPIHandler(services, handlers)
    _rems = RemsAPIHandler(services, handlers)
    _file = FilesAPIHandler(services, handlers)
    _health = HealthAPIHandler(services, handlers)
    _key = KeyAPIHandler(services, handlers)
    _user = UserAPIHandler(services, handlers)
    _auth = AuthAPIHandler(deployment_services.auth)

    # API router (authorization required).
    #

    api_router = APIRouter(prefix=config.API_PREFIX_V1)

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
    if profile.import_endpoints:
        api_router.add_api_route(
            "/import",
            _object.import_submission,
            methods=POST,
            tags=submission_tag,
            openapi_extra=openapi_multipart,
            summary="Import a dataset accessioned and archived outside SD Submit",
        )
        api_router.add_api_route(
            "/import/{submissionId}",
            _object.delete_imported_submission,
            methods=DELETE,
            tags=submission_tag,
            summary="Delete an unpublished imported submission",
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
    if profile.submission_endpoints:
        api_router.add_api_route(
            "/submissions",
            _submission.create_submission,
            methods=POST,
            status_code=status.HTTP_201_CREATED,
            tags=submission_tag,
        )
        api_router.add_api_route(
            "/submissions/{submissionId}", _submission.update_submission, methods=PATCH, tags=submission_tag
        )
        api_router.add_api_route(
            "/submissions/{submissionId}",
            _submission.delete_submission,
            methods=DELETE,
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

    # User routes.
    api_router.add_api_route("/users", _user.get_user, methods=GET, tags=user_tag, summary="Get user information")

    # Publish routes.
    api_router.add_api_route(
        "/publish/{submissionId}", _publish_submission.publish_submission, methods=PATCH, tags=submission_tag
    )

    # Key routes.
    if profile.api_key_endpoints:
        api_router.add_api_route("/api/keys", _key.create_api_key, methods=POST, tags=key_tag)
        api_router.add_api_route("/api/keys", _key.delete_api_key, methods=DELETE, tags=key_tag)
        api_router.add_api_route("/api/keys", _key.get_api_keys, methods=GET, tags=key_tag)

    # File routes.
    if profile.bucket_endpoints:
        api_router.add_api_route("/buckets", _file.get_project_buckets, methods=GET, tags=bucket_tag)
        api_router.add_api_route("/buckets/{bucket}/files", _file.get_files_in_bucket, methods=GET, tags=bucket_tag)
        api_router.add_api_route("/buckets/{bucket}", _file.grant_access_to_bucket, methods=["PUT"], tags=bucket_tag)
        api_router.add_api_route("/buckets/{bucket}", _file.check_bucket_access, methods=HEAD, tags=bucket_tag)

    # REMS routes.
    api_router.add_api_route("/rems", _rems.get_organisations, methods=GET, tags=rems_tag)

    # Auth router (authorization not required).
    #

    auth_router = None
    if profile.login_endpoints:
        auth_router = APIRouter(prefix=config.API_PREFIX, tags=["Authentication"])
        auth_router.add_api_route(path="/login", endpoint=_auth.login, methods=GET)
        auth_router.add_api_route(path="/callback", endpoint=_auth.callback, methods=GET, include_in_schema=False)
        auth_router.add_api_route(path="/logout", endpoint=_auth.logout, methods=GET)

    # Sync router (requires a token signed by the sync client).
    #

    sync_router = None
    if sync_config().SYNC_CLIENTS:
        # Add sync routes only if SYNC_CLIENTS has been defined.
        _sync = SyncAPIHandler(services, handlers, deployment_services.sync_provider)
        sync_router = APIRouter(
            prefix=config.API_PREFIX_SYNC,
            tags=["Sync"],
            # /sync endpoints require a token verified with a SYNC_CLIENTS public key.
            dependencies=[Depends(verify_sync)],
        )
        sync_router.add_api_route("", _sync.list_published_submissions, methods=GET)
        if deployment_services.sync_provider:
            sync_router.add_api_route(
                "/{submissionId}",
                _sync.get_submission_metadata,
                methods=GET,
                # Metadata is returned as a zip.
                response_class=Response,
                responses={status.HTTP_200_OK: {"content": {"application/zip": {}}}},
            )

    # Health router (authorization not required).
    #

    health_router = APIRouter(prefix=config.API_PREFIX, tags=["Health"])
    health_router.add_api_route("/health", _health.get_health_status, methods=GET)

    # OpenAPI router (authorization not required).
    #

    openapi_router = APIRouter(prefix=config.API_PREFIX)

    # OpenAPI redirect.
    @openapi_router.get("/", include_in_schema=False)
    async def redirect_to_docs() -> RedirectResponse:
        return RedirectResponse(url="/docs", status_code=status.HTTP_302_FOUND)

    # Add routers.

    app.include_router(api_router)
    if auth_router:
        app.include_router(auth_router)
    if sync_router:
        app.include_router(sync_router)
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

        # Document the problem JSON error responses.
        add_error_responses(openapi_schema)

        # Add security scheme.
        openapi_schema["components"]["securitySchemes"] = {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
            }
        }

        def _apply_security(router: APIRouter, security: list[dict[str, list[str]]]) -> None:
            """Apply a security requirement to the routes of one router."""
            for _route in router.routes:
                if isinstance(_route, APIRoute):
                    path = _route.path
                    methods: list[str] = list(_route.methods) or []
                    for method in methods:
                        method = method.lower()
                        if path in openapi_schema["paths"] and method in openapi_schema["paths"][path]:
                            openapi_schema["paths"][path][method]["security"] = security

        # Apply security scheme to API routes.
        _apply_security(api_router, [{"oidc": []}])

        # The sync routes are authorized with the sync service account token instead.
        if sync_router:
            _apply_security(sync_router, [{"bearerAuth": []}])

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]

    # ASGI middleware is used to handle auditing, authentication and sessions,
    # before any FastAPI/Starlette route is processed.
    if session:
        # The session is managed by the caller.
        return AuditMiddleware(AuthMiddleware(app, auth_service))
    return add_middlewares(app, auth_service, _session_context)


def main() -> None:
    """Launch the FastAPI server."""
    host = "0.0.0.0"  # nosec
    port = deployment_config().SERVER_PORT
    if port is None:
        port = deployment_profile().default_port

    LOG.info("Starting %s server %s on port %s", deployment_config().DEPLOYMENT.value, __version__, port)

    # Once, before the workers start.
    if database_config().DATABASE_MIGRATE:
        LOG.info("Applying database migrations")
        migrate_schema()

    # log_config=None stops uvicorn from setting up its own log handlers and formats. Its logs then
    # go to the root logger and are written in LOG_FORMAT like every other log; as a library, uvicorn
    # logs warnings and errors only, so its request and startup lines are not written
    # (helpers/logger.py).
    uvicorn.run(create_app(), host=host, port=port, loop="uvloop", log_config=None)


if __name__ == "__main__":
    main()
