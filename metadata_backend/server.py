"""Functions to launch backend server."""

import asyncio
import logging
from typing import TypeVar

import uvloop
from aiohttp import web
from aiohttp.web_routedef import AbstractRouteDef

from .api.handlers.auth import AuthAPIHandler
from .api.handlers.files import FilesAPIHandler
from .api.handlers.health import HealthAPIHandler
from .api.handlers.key import KeyAPIHandler
from .api.handlers.object import ObjectAPIHandler
from .api.handlers.publish import PublishAPIHandler
from .api.handlers.rems import RemsAPIHandler
from .api.handlers.restapi import RESTAPIServiceHandlers, RESTAPIServices
from .api.handlers.static import html_handler_factory
from .api.handlers.submission import SubmissionAPIHandler
from .api.handlers.user import UserAPIHandler
from .api.middlewares import AUTH_SERVICE, authorization, http_error_handler
from .api.services.auth import AuthService
from .api.services.file import S3AllasFileProviderService
from .api.services.project import CscProjectService, NbisProjectService, ProjectService
from .conf.conf import (
    API_PREFIX,
    DEPLOYMENT_CSC,
    DEPLOYMENT_NBIS,
    swagger_static_path,
)
from .conf.deployment import deployment_config
from .database.postgres.repositories.api_key import ApiKeyRepository
from .database.postgres.repositories.file import FileRepository
from .database.postgres.repositories.object import ObjectRepository
from .database.postgres.repositories.registration import RegistrationRepository
from .database.postgres.repositories.submission import SubmissionRepository
from .database.postgres.repository import create_engine, create_session_factory
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


async def init() -> web.Application:
    """
    Create the web application.

    :returns: The created web application.
    """
    middlewares = [http_error_handler, authorization]

    api = web.Application(middlewares=middlewares)  # type: ignore
    server = web.Application()

    # Override server header for security reasons.
    async def override_server_header(_: web.Request, response: web.StreamResponse) -> None:
        response.headers["Server"] = "metadata"

    api.on_response_prepare.append(override_server_header)
    server.on_response_prepare.append(override_server_header)

    # Initialise logging.
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

    # Create database engine.
    engine = await create_engine()

    async def dispose_engine(_: web.Application) -> None:
        await engine.dispose()

    server.on_cleanup.append(dispose_engine)

    # Create database session factory.
    session_factory = create_session_factory(engine)

    # Create database repositories.
    submission_repository = SubmissionRepository(session_factory)
    object_repository = ObjectRepository(session_factory)
    registration_repository = RegistrationRepository(session_factory)
    file_repository = FileRepository(session_factory)
    api_key_repository = ApiKeyRepository(session_factory)

    # Create database services.
    submission_service = SubmissionService(submission_repository, registration_repository)
    object_service = ObjectService(object_repository)
    registration_service = RegistrationService(registration_repository)
    file_service = FileService(file_repository)
    auth_service = AuthService(api_key_repository)

    # Create project service.
    project_service: ProjectService | None = None

    config = deployment_config()
    if config.DEPLOYMENT == DEPLOYMENT_NBIS:
        project_service = NbisProjectService()
    elif config.DEPLOYMENT == DEPLOYMENT_CSC:
        project_service = CscProjectService()

    # Create S3 Allas service.
    file_provider_service = S3AllasFileProviderService()

    # Create service handlers.
    def _create_handler(handler: ServiceHandlerType) -> ServiceHandlerType:
        server.on_cleanup.append(lambda _: handler.close())
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

    # Create API handlers.
    services = RESTAPIServices(
        session_factory=session_factory,
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

    handlers = RESTAPIServiceHandlers(
        datacite=datacite_handler,
        pid=pid_handler,
        metax=metax_handler,
        ror=ror_handler,
        rems=rems_handler,
        keystone=keystone_handler,
        auth=auth_handler,
        admin=admin_handler,
        database=DatabaseHealthHandler(engine),
    )

    _object = ObjectAPIHandler(services, handlers)
    _submission = SubmissionAPIHandler(services, handlers)
    _publish_submission = PublishAPIHandler(services, handlers)
    _rems = RemsAPIHandler(services, handlers)
    _file = FilesAPIHandler(services, handlers)
    _health = HealthAPIHandler(services, handlers)
    _key = KeyAPIHandler(services, handlers)
    _user = UserAPIHandler(services, handlers)

    # Make AccessService available to authorization middleware.
    api[AUTH_SERVICE] = auth_service

    # Configure API routes.
    api_routes = [
        web.post("/submit/{workflow}", _object.add_submission),
        web.patch("/submit/{workflow}/{submissionId}", _object.update_submission),
        web.delete("/submit/{workflow}/{submissionId}", _object.delete_submission),
        web.head("/submit/{workflow}/{submissionId}", _object.is_submission),
        web.get("/submissions/{submissionId}/objects", _object.list_objects),
        web.get("/submissions/{submissionId}/objects/docs", _object.get_objects),
        # Submissions requests.
        web.get("/submissions", _submission.get_submissions),
        web.post("/submissions", _submission.post_submission),  # TODO(improve): deprecate endpoint
        web.get("/submissions/{submissionId}", _submission.get_submission),
        web.get("/submissions/{submissionId}/files", _submission.get_submission_files),
        web.get("/submissions/{submissionId}/registrations", _submission.get_registrations),
        web.patch("/submissions/{submissionId}", _submission.patch_submission),  # TODO(improve): deprecate endpoint
        web.delete("/submissions/{submissionId}", _submission.delete_submission),  # TODO(improve): deprecate endpoint
        web.post("/submissions/{submissionId}/ingest", _submission.post_data_ingestion),
        # User requests.
        web.get("/users", _user.get_user),
        # Publish requests.
        web.patch("/publish/{submissionId}", _publish_submission.publish_submission),
        # Key requests.
        web.post("/api/keys", _key.post_api_key),
        web.delete("/api/keys", _key.delete_api_key),
        web.get("/api/keys", _key.get_api_keys),
        # File requests.
        web.get("/buckets", _file.get_project_buckets),
        web.get("/buckets/{bucket}/files", _file.get_files_in_bucket),
        web.put("/buckets/{bucket}", _file.grant_access_to_bucket),
        web.head("/buckets/{bucket}", _file.check_bucket_access),
        # REMS.
        web.get("/rems", _rems.get_organisations),
    ]

    api.add_routes(api_routes)
    server.add_subapp(API_PREFIX, api)
    LOG.info("API configurations and routes loaded")

    _auth = AuthAPIHandler(auth_handler)
    auth_routes = get_auth_routes(_auth, config.DEPLOYMENT)
    server.add_routes(auth_routes)
    LOG.info("AAI routes loaded")

    health_routes = [
        web.get("/health", _health.get_health_status),
    ]
    server.add_routes(health_routes)
    LOG.info("Health routes loaded")

    if swagger_static_path.exists():
        swagger_handler = html_handler_factory(swagger_static_path)
        server.router.add_get("/swagger", swagger_handler)
        LOG.info("Swagger routes loaded")

    return server


def get_auth_routes(_auth: AuthAPIHandler, deployment: str) -> list[AbstractRouteDef]:
    """Get the authentication routes depending on deployment configuration."""
    routes: list[AbstractRouteDef] = [
        web.get("/aai", _auth.login),  # TODO(improve): deprecate endpoint
        web.get("/login", _auth.login),
        web.get("/callback", _auth.callback),
        web.get("/logout", _auth.logout),
    ]
    if deployment == DEPLOYMENT_NBIS:
        routes = [
            web.get("/login", _auth.login_cli),
            web.get("/callback", _auth.callback_cli),
        ]
    return routes


def main() -> None:
    """Launch the server."""
    config = deployment_config()
    host = "0.0.0.0"  # nosec
    port = 5430 if config.DEPLOYMENT == DEPLOYMENT_CSC else 5431
    web.run_app(init(), host=host, port=port, shutdown_timeout=0)


if __name__ == "__main__":
    main()
