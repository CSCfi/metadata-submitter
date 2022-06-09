"""Functions to launch backend server."""

import asyncio

import uvloop
import base64
from aiohttp import web
from cryptography.fernet import Fernet
from typing import List, Any

from .api.auth import AccessHandler
from .api.handlers.restapi import RESTAPIHandler
from .api.handlers.static import StaticHandler, html_handler_factory
from .api.handlers.submission import SubmissionAPIHandler
from .api.handlers.object import ObjectAPIHandler
from .api.handlers.xml_submission import XMLSubmissionAPIHandler
from .api.handlers.template import TemplatesAPIHandler
from .api.handlers.user import UserAPIHandler
from .api.health import HealthHandler
from .api.middlewares import http_error_handler, check_session
from .conf.conf import (
    aai_config,
    create_db_client,
    frontend_static_files,
    swagger_static_path,
    API_PREFIX,
)
from .helpers.logger import LOG
import aiohttp_session
import aiohttp_session.cookie_storage

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


async def init(
    inject_middleware: List[Any] = [],
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

    _schema = RESTAPIHandler()
    _object = ObjectAPIHandler()
    _submission = SubmissionAPIHandler()
    _user = UserAPIHandler()
    _xml_submission = XMLSubmissionAPIHandler()
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
        web.put("/submissions/{submissionId}/doi", _submission.put_submission_doi),
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
    api.add_routes(api_routes)
    LOG.info("API configurations and routes loaded")

    sec_key = base64.urlsafe_b64decode(Fernet.generate_key())
    session_middleware = aiohttp_session.session_middleware(
        aiohttp_session.cookie_storage.EncryptedCookieStorage(sec_key)
    )
    server = web.Application(middlewares=[session_middleware])
    server.add_subapp(API_PREFIX, api)

    if aai_config["enabled"]:
        _access = AccessHandler(aai_config)
        aai_routes = [
            web.get("/aai", _access.login),
            web.get("/logout", _access.logout),
            web.get("/callback", _access.callback),
        ]
        server.add_routes(aai_routes)
        LOG.info("AAI routes loaded")
    _health = HealthHandler()
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
