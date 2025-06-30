"""Functions to launch backend server."""

import asyncio
from typing import Any, Optional

import uvloop
from aiohttp import web

from .api.auth import AAIServiceHandler, AccessHandler
from .api.handlers import auth as APIKeyHandler
from .api.handlers import user as UserHandler
from .api.handlers.files import FilesAPIHandler
from .api.handlers.object import ObjectAPIHandler
from .api.handlers.publish import PublishSubmissionAPIHandler
from .api.handlers.rems_proxy import RemsAPIHandler
from .api.handlers.restapi import RESTAPIHandler
from .api.handlers.static import StaticHandler, html_handler_factory
from .api.handlers.submission import SubmissionAPIHandler
from .api.handlers.xml_submission import XMLSubmissionAPIHandler
from .api.health import HealthHandler
from .api.middlewares import authorization, http_error_handler
from .api.services.auth import AccessService
from .api.services.project import CscLdapProjectService
from .conf.conf import API_PREFIX, aai_config, create_db_client, frontend_static_files, swagger_static_path
from .database.postgres.repository import ApiKeyRepository, create_engine, create_session_factory
from .helpers.logger import LOG
from .services.admin_service_handler import AdminServiceHandler
from .services.datacite_service_handler import DataciteServiceHandler
from .services.metax_service_handler import MetaxServiceHandler
from .services.pid_ms_handler import PIDServiceHandler
from .services.rems_service_handler import RemsServiceHandler
from .services.taxonomy_search_handler import TaxonomySearchHandler

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


async def init(
    inject_middleware: Optional[list[Any]] = None,
) -> web.Application:
    """Initialise server and setup routes.

    Routes should be setup by adding similar paths one after the another. (i.e.
    ``POST`` and ``GET`` for same path grouped together). Handler method names should
    be used for route names, so they're easy to use in other parts of the
    application.

    .. note:: if using variable resources (such as ``{schema}``), add
              specific ones on top of more generic ones.

    :param inject_middleware: list of middlewares to inject
    :returns: Web Application
    """
    middlewares = [http_error_handler, authorization]
    if inject_middleware:
        middlewares = middlewares + inject_middleware

    api = web.Application(middlewares=middlewares)  # type: ignore
    server = web.Application()

    # Initialise shared resources.
    #

    # Mongo.
    db_client = create_db_client()
    api["db_client"] = db_client
    server["db_client"] = db_client

    # Repositories.
    engine = await create_engine()
    session_factory = create_session_factory(engine)
    api_key_repository = ApiKeyRepository(session_factory)

    # Project service.
    project_service = CscLdapProjectService()
    api["project_service"] = project_service
    server["project_service"] = project_service

    # Access service.
    access_service = AccessService(api_key_repository)
    api["access_service"] = access_service
    server["access_service"] = access_service

    # Initialize handlers.
    #

    metax_handler = MetaxServiceHandler()
    datacite_handler = DataciteServiceHandler()
    pid_handler = PIDServiceHandler()
    rems_handler = RemsServiceHandler()
    aai_handler = AAIServiceHandler()
    taxonomy_handler = TaxonomySearchHandler()
    admin_handler = AdminServiceHandler()

    async def close_http_clients(_: web.Application) -> None:
        """Close http client session."""
        await metax_handler.http_client_close()
        await datacite_handler.http_client_close()
        await rems_handler.http_client_close()
        await admin_handler.http_client_close()

    async def on_prepare(_: web.Request, response: web.StreamResponse) -> None:
        """Modify Server headers."""
        response.headers["Server"] = "metadata"

    server.on_response_prepare.append(on_prepare)

    server.on_shutdown.append(close_http_clients)

    _common_api_handler = RESTAPIHandler()
    _object = ObjectAPIHandler(
        metax_handler=metax_handler,
        datacite_handler=datacite_handler,
        rems_handler=rems_handler,
        admin_handler=admin_handler,
        pid_handler=pid_handler,
    )
    _submission = SubmissionAPIHandler(
        metax_handler=metax_handler,
        datacite_handler=datacite_handler,
        rems_handler=rems_handler,
        admin_handler=admin_handler,
        pid_handler=pid_handler,
    )
    _publish_submission = PublishSubmissionAPIHandler(
        metax_handler=metax_handler,
        datacite_handler=datacite_handler,
        rems_handler=rems_handler,
        admin_handler=admin_handler,
        pid_handler=pid_handler,
    )
    _xml_submission = XMLSubmissionAPIHandler(
        metax_handler=metax_handler,
        datacite_handler=datacite_handler,
        rems_handler=rems_handler,
        admin_handler=admin_handler,
        pid_handler=pid_handler,
    )
    _file = FilesAPIHandler()
    api_routes = [
        # retrieve workflows
        web.get("/workflows", _common_api_handler.get_workflows),
        web.get("/workflows/{workflow}", _common_api_handler.get_workflow_request),
        # retrieve schema and information about it
        web.get("/schemas", _common_api_handler.get_schema_types),
        web.get("/schemas/{schema}", _common_api_handler.get_json_schema),
        # metadata objects operations
        web.post("/objects/{schema}", _object.post_object),
        web.get("/objects/{schema}/{accessionId}", _object.get_object),
        web.put("/objects/{schema}/{accessionId}", _object.put_object),
        web.patch("/objects/{schema}/{accessionId}", _object.patch_object),
        web.delete("/objects/{schema}/{accessionId}", _object.delete_object),
        # draft objects operations
        web.post("/drafts/{schema}", _object.post_object),
        web.get("/drafts/{schema}/{accessionId}", _object.get_object),
        web.put("/drafts/{schema}/{accessionId}", _object.put_object),
        web.patch("/drafts/{schema}/{accessionId}", _object.patch_object),
        web.delete("/drafts/{schema}/{accessionId}", _object.delete_object),
        # submissions operations
        web.get("/submissions", _submission.get_submissions),
        web.post("/submissions", _submission.post_submission),
        web.get("/submissions/{submissionId}", _submission.get_submission),
        web.get("/submissions/{submissionId}/files", _submission.get_submission_files),
        web.patch("/submissions/{submissionId}/doi", _submission.patch_submission_doi_rems),
        web.patch("/submissions/{submissionId}/rems", _submission.patch_submission_doi_rems),
        web.patch("/submissions/{submissionId}/folder", _submission.patch_submission_linked_folder),
        web.patch("/submissions/{submissionId}/files", _submission.patch_submission_files),
        web.patch("/submissions/{submissionId}", _submission.patch_submission),
        web.delete("/submissions/{submissionId}", _submission.delete_submission),
        web.delete("/submissions/{submissionId}/files/{fileId}", _submission.delete_submission_files),
        web.post("/submissions/{submissionId}/ingest", _submission.post_data_ingestion),
        # user operations
        web.get("/users", UserHandler.get_user),
        # publish submissions - endpoint for general case
        web.patch("/publish/{submissionId}", _publish_submission.publish_submission),
        # announce submissions - endpoint for BP case
        web.patch("/announce/{submissionId}", _publish_submission.publish_submission),
        # api key operations
        web.post("/api/keys", APIKeyHandler.post_api_key),
        web.delete("/api/keys", APIKeyHandler.delete_api_key),
        web.get("/api/keys", APIKeyHandler.get_api_keys),
        # XML submission
        web.post("/submit/{workflow}", _xml_submission.submit),
        # validate
        web.post("/validate", _xml_submission.validate),
        # File operations
        web.get("/files", _file.get_project_files),
        web.post("/files", _file.post_project_files),
        web.delete("/files/{projectId}", _file.delete_project_files),
    ]
    _rems = RemsAPIHandler(
        metax_handler=metax_handler,
        datacite_handler=datacite_handler,
        rems_handler=rems_handler,
        admin_handler=admin_handler,
        pid_handler=pid_handler,
    )
    api_routes.append(web.get("/rems", _rems.get_workflows_licenses_from_rems))
    api_routes.append(web.get("/taxonomy", taxonomy_handler.get_query_results))

    api.add_routes(api_routes)
    server.add_subapp(API_PREFIX, api)
    LOG.info("API configurations and routes loaded")

    _access = AccessHandler(aai_config)
    aai_routes = [
        web.get("/aai", _access.login),
        web.get("/callback", _access.callback),
        web.get("/logout", _access.logout),
    ]
    server.add_routes(aai_routes)
    LOG.info("AAI routes loaded")
    _health = HealthHandler(
        metax_handler=metax_handler,
        datacite_handler=datacite_handler,
        pid_handler=pid_handler,
        rems_handler=rems_handler,
        aai_handler=aai_handler,
        admin_handler=admin_handler,
    )
    health_routes = [
        web.get("/health", _health.get_health_status),
    ]
    server.add_routes(health_routes)
    LOG.info("Health routes loaded")
    if swagger_static_path.exists():
        swagger_handler = html_handler_factory(swagger_static_path)
        server.router.add_get("/swagger", swagger_handler)
        LOG.info("Swagger routes loaded")

    # These should be the last routes added, as they are a catch-all
    if frontend_static_files.exists():
        _static = StaticHandler(frontend_static_files)
        frontend_routes = [
            web.static("/static", _static.setup_static()),
            web.get("/{path:.*}", _static.frontend),
        ]
        server.add_routes(frontend_routes)
        LOG.info("Frontend routes loaded")

    # Cleanup shared resources.
    #

    # Sqlalcehemy.
    async def dispose_engine(_: web.Application) -> None:
        """Dispose the SQLAlchemy engine."""
        await engine.dispose()

    server.on_cleanup.append(dispose_engine)

    return server


def main() -> None:
    """Launch the server."""
    host = "0.0.0.0"  # nosec
    port = 5430
    web.run_app(init(), host=host, port=port, shutdown_timeout=0)
    LOG.info("Started server on %s:%d", host, port)


if __name__ == "__main__":
    main()
