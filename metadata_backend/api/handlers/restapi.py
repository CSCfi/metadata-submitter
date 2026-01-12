"""Base class for HTTP API handlers."""

import json
from typing import Any

from aiohttp import web
from aiohttp.web import Request
from pydantic import BaseModel, ConfigDict

from ...database.postgres.repository import SessionFactory
from ...database.postgres.services.file import FileService
from ...database.postgres.services.object import ObjectService
from ...database.postgres.services.registration import RegistrationService
from ...database.postgres.services.submission import SubmissionService
from ...helpers.logger import LOG
from ...services.admin_service import AdminServiceHandler
from ...services.auth_service import AuthServiceHandler
from ...services.datacite_service import DataciteServiceHandler
from ...services.keystone_service import KeystoneServiceHandler
from ...services.metax_service import MetaxServiceHandler
from ...services.pid_service import PIDServiceHandler
from ...services.rems_service import RemsServiceHandler
from ...services.ror_service import RorServiceHandler
from ...services.service_handler import HealthHandler
from ..services.auth import AuthService
from ..services.file import FileProviderService
from ..services.project import ProjectService


class RESTAPIServices(BaseModel):
    """Services used by HTTP API handlers."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Session factory.
    session_factory: SessionFactory
    # Database services.
    submission: SubmissionService
    object: ObjectService
    registration: RegistrationService
    file: FileService
    # Auth service.
    auth: AuthService
    # Project service.
    project: ProjectService
    # File provider service.
    file_provider: FileProviderService


class RESTAPIServiceHandlers(BaseModel):
    """Service handlers used by HTTP API handlers."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    datacite: DataciteServiceHandler
    pid: PIDServiceHandler
    metax: MetaxServiceHandler
    ror: RorServiceHandler
    rems: RemsServiceHandler
    keystone: KeystoneServiceHandler
    auth: AuthServiceHandler
    admin: AdminServiceHandler | None = None
    database: HealthHandler


class RESTAPIHandler:
    """Base class for HTTP API handlers."""

    def __init__(self, services: RESTAPIServices, handlers: RESTAPIServiceHandlers) -> None:
        """Base class for HTTP API handlers."""

        self._services = services
        self._handlers = handlers

    @staticmethod
    async def get_json_dict(req: Request) -> dict[str, Any]:
        """Get JSON data from the request body.

        :param req: HTTP request
        :returns: JSON data from the request body.
        """
        try:
            data = await req.json()
        except json.decoder.JSONDecodeError as e:
            reason = f"JSON is not correctly formatted: {e}"
            LOG.exception(reason)
            raise web.HTTPBadRequest(reason=reason) from e

        if not isinstance(data, dict):
            reason = f"Expected JSON object (dict) in request body, got {type(data).__name__}"
            LOG.warning(reason)
            raise web.HTTPBadRequest(reason=reason)

        return data

    @staticmethod
    def get_mandatory_param(req: Request, name: str) -> str:
        """Get mandatory query parameter.

        :param req: HTTP request
        :param name: name of query parameter
        :returns: The query parameter value
        """
        param = req.query.get(name)
        if param is None:
            reason = f"Missing required query parameter '{name}'"
            LOG.error(reason)
            raise web.HTTPBadRequest(reason=reason)
        return param
