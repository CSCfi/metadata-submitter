"""Base class for HTTP API handlers."""

from pydantic import BaseModel, ConfigDict

from ...database.postgres.services.file import FileService
from ...database.postgres.services.object import ObjectService
from ...database.postgres.services.registration import RegistrationService
from ...database.postgres.services.submission import SubmissionService
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

    datacite: DataciteServiceHandler | None
    pid: PIDServiceHandler | None
    metax: MetaxServiceHandler | None
    ror: RorServiceHandler | None
    rems: RemsServiceHandler
    keystone: KeystoneServiceHandler | None
    auth: AuthServiceHandler
    admin: AdminServiceHandler | None = None
    database: HealthHandler


class RESTAPIHandler:
    """Base class for HTTP API handlers."""

    def __init__(self, services: RESTAPIServices, handlers: RESTAPIServiceHandlers) -> None:
        """Base class for HTTP API handlers."""

        self._services = services
        self._handlers = handlers
