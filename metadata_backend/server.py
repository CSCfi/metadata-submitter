"""Functions to launch backend server."""

import asyncio
import base64
from typing import Any, List, Optional

import aiohttp_session
import aiohttp_session.cookie_storage
import uvloop
from aiohttp import web
from cryptography.fernet import Fernet

from .api.auth import AAIServiceHandler, AccessHandler
from .api.handlers.object import ObjectAPIHandler
from .api.handlers.rems_proxy import RemsAPIHandler
from .api.handlers.restapi import RESTAPIHandler
from .api.handlers.static import StaticHandler, html_handler_factory
from .api.handlers.submission import SubmissionAPIHandler
from .api.handlers.template import TemplatesAPIHandler
from .api.handlers.user import UserAPIHandler
from .api.handlers.xml_submission import XMLSubmissionAPIHandler
from .api.health import HealthHandler
from .api.middlewares import check_session, http_error_handler
from .conf.conf import (
    API_PREFIX,
    REMS_ENABLED,
    aai_config,
    create_db_client,
    frontend_static_files,
    swagger_static_path,
)
from .helpers.logger import LOG
from .services.datacite_service_handler import DataciteServiceHandler
from .services.metax_service_handler import MetaxServiceHandler
from .services.rems_service_handler import RemsServiceHandler

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


async def init(
    inject_middleware: Optional[List[Any]] = None,
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
    middlewares = [http_error_handler, check_session]
    if inject_middleware:
        middlewares = middlewares + inject_middleware
    api = web.Application(middlewares=middlewares)

    sec_key = base64.urlsafe_b64decode(Fernet.generate_key())
    session_middleware = aiohttp_session.session_middleware(
        aiohttp_session.cookie_storage.EncryptedCookieStorage(sec_key)
    )
    server = web.Application(middlewares=[session_middleware])

    metax_handler = MetaxServiceHandler()
    datacite_handler = DataciteServiceHandler()
    rems_handler = RemsServiceHandler()
    aai_handler = AAIServiceHandler()

    async def close_http_clients(_: web.Application) -> None:
        """Close http client session."""
        await metax_handler.http_client_close()
        await datacite_handler.http_client_close()
        await rems_handler.http_client_close()

    async def on_prepare(_: web.Request, response: web.StreamResponse) -> None:
        """Modify Server headers."""
        response.headers["Server"] = "metadata"

    server.on_response_prepare.append(on_prepare)

    server.on_shutdown.append(close_http_clients)

    _schema = RESTAPIHandler()
    _object = ObjectAPIHandler(
        metax_handler=metax_handler, datacite_handler=datacite_handler, rems_handler=rems_handler
    )
    _submission = SubmissionAPIHandler(
        metax_handler=metax_handler, datacite_handler=datacite_handler, rems_handler=rems_handler
    )
    _user = UserAPIHandler()
    _xml_submission = XMLSubmissionAPIHandler(
        metax_handler=metax_handler, datacite_handler=datacite_handler, rems_handler=rems_handler
    )
    _template = TemplatesAPIHandler()
    api_routes = [
        # retrieve schema and information about it
        web.get("/schemas", _schema.get_schema_types),
        web.get("/schemas/{schema}", _schema.get_json_schema),
        # metadata objects operations
        web.get("/objects/{schema}", _object.query_objects),
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
        # template objects operations
        web.get("/templates", _template.get_templates),
        web.post("/templates/{schema}", _template.post_template),
        web.get("/templates/{schema}/{accessionId}", _template.get_template),
        web.patch("/templates/{schema}/{accessionId}", _template.patch_template),
        web.delete("/templates/{schema}/{accessionId}", _template.delete_template),
        # submissions operations
        web.get("/submissions", _submission.get_submissions),
        web.post("/submissions", _submission.post_submission),
        web.get("/submissions/{submissionId}", _submission.get_submission),
        web.put("/submissions/{submissionId}/doi", _submission.put_submission_path),
        web.patch("/submissions/{submissionId}", _submission.patch_submission),
        web.delete("/submissions/{submissionId}", _submission.delete_submission),
        # publish submissions
        web.patch("/publish/{submissionId}", _submission.publish_submission),
        # users operations
        web.get("/users/{userId}", _user.get_user),
        web.delete("/users/{userId}", _user.delete_user),
        # submit
        web.post("/submit", _xml_submission.submit),
        # validate
        web.post("/validate", _xml_submission.validate),
    ]
    if REMS_ENABLED:
        LOG.info("REMS is enabled, adding to list of api routes")
        api_routes.append(
            web.put("/submissions/{submissionId}/dac", _submission.put_submission_path),
        )
        _rems = RemsAPIHandler(
            metax_handler=metax_handler, datacite_handler=datacite_handler, rems_handler=rems_handler
        )
        api_routes.append(web.get("/rems", _rems.get_workflows_licenses_from_rems))

    api.add_routes(api_routes)
    server.add_subapp(API_PREFIX, api)
    LOG.info("API configurations and routes loaded")

    _access = AccessHandler(aai_config)
    aai_routes = [
        web.get("/aai", _access.login),
        web.get("/logout", _access.logout),
        web.get("/callback", _access.callback),
    ]
    server.add_routes(aai_routes)
    LOG.info("AAI routes loaded")
    _health = HealthHandler(
        metax_handler=metax_handler,
        datacite_handler=datacite_handler,
        rems_handler=rems_handler,
        aai_handler=aai_handler,
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

    db_client = create_db_client()
    api["db_client"] = db_client
    server["db_client"] = db_client
    LOG.info("Database client loaded")
    return server


def main() -> None:
    """Launch the server."""
    host = "0.0.0.0"  # nosec
    port = 5430
    web.run_app(init(), host=host, port=port, shutdown_timeout=0)
    LOG.info(f"Started server on {host}:{port}")


if __name__ == "__main__":
    main()
