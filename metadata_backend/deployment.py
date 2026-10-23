"""Deployment profiles.

A deployment profile holds the deployment-specific wiring of the application: the services and
service handlers it uses, and the endpoints it serves. The submission workflow of a deployment
is on the Deployment enum.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar, Protocol, TypeVar, override

from .api.services.bigpicture import BigpictureSyncMetadataProvider, read_bp_public_key
from .api.services.crypt import Crypt4GHPublicKeyProvider
from .api.services.file import FileProviderService, S3AllasFileProviderService, S3InboxSDAService
from .api.services.project import CscProjectService, NbisProjectService, ProjectService
from .api.services.rems import RemsLicenseProvider
from .api.services.submission.bigpicture_policy import BigpictureRemsLicenseProvider
from .api.services.sync import SyncMetadataProvider
from .conf.deployment import Deployment, deployment_config
from .database.postgres.services.file import FileService
from .database.postgres.services.object import ObjectService
from .services.admin_service import AdminServiceHandler
from .services.auth_service import AuthServiceHandler
from .services.datacite_service import DataciteServiceHandler
from .services.keystone_service import KeystoneServiceHandler
from .services.metax_service import MetaxServiceHandler
from .services.pid_service import PIDServiceHandler
from .services.ror_service import RorServiceHandler
from .services.service_handler import ServiceHandler

ServiceHandlerType = TypeVar("ServiceHandlerType", bound=ServiceHandler)


class CreateHandler(Protocol):
    """Registers a service handler with the application and returns it."""

    def __call__(self, handler: ServiceHandlerType) -> ServiceHandlerType: ...


@dataclass
class DeploymentServices:
    """Deployment-specific services and service handlers."""

    project: ProjectService
    file_provider: FileProviderService
    metax: MetaxServiceHandler | None = None
    ror: RorServiceHandler | None = None
    pid: PIDServiceHandler | None = None
    keystone: KeystoneServiceHandler | None = None
    auth: AuthServiceHandler | None = None
    datacite: DataciteServiceHandler | None = None
    admin: AdminServiceHandler | None = None
    license_provider: RemsLicenseProvider | None = None
    sync_provider: SyncMetadataProvider | None = None


class DeploymentProfile(ABC):
    """Deployment-specific wiring of the application."""

    deployment: ClassVar[Deployment]

    # The port the server listens on, unless SERVER_PORT is set.
    default_port: ClassVar[int]

    # Enables the create, update and delete {API_PREFIX_V1}/submissions endpoints.
    submission_endpoints: ClassVar[bool]

    # Enables {API_PREFIX_V1}/api/keys endpoints.
    api_key_endpoints: ClassVar[bool]

    # Enables {API_PREFIX_V1}/buckets endpoints.
    bucket_endpoints: ClassVar[bool]

    # Enables the OIDC {API_PREFIX}/login, {API_PREFIX}/callback and {API_PREFIX}/logout endpoints.
    login_endpoints: ClassVar[bool]

    # Enables a background task that ingests the files of published submissions with the SDA Admin API.
    sda_ingest: ClassVar[bool]

    # Enables the {API_PREFIX_V1}/import endpoint, which creates a submission from a dataset
    # accessioned and archived outside SD Submit.
    import_endpoints: ClassVar[bool]

    @abstractmethod
    def create_services(
        self, create_handler: CreateHandler, object_service: ObjectService, file_service: FileService
    ) -> DeploymentServices:
        """
        Create the deployment-specific services and service handlers.

        :param create_handler: Registers a service handler with the application.
        :param object_service: The metadata object database service.
        :param file_service: The file database service.
        :returns: The deployment-specific services and service handlers.
        """


class CscDeploymentProfile(DeploymentProfile):
    """CSC deployment."""

    deployment = Deployment.CSC
    default_port = 5430
    submission_endpoints = True
    api_key_endpoints = True
    bucket_endpoints = True
    login_endpoints = True
    sda_ingest = False
    import_endpoints = False

    @override
    def create_services(
        self, create_handler: CreateHandler, object_service: ObjectService, file_service: FileService
    ) -> DeploymentServices:
        project = CscProjectService()
        metax = create_handler(MetaxServiceHandler())
        ror = create_handler(RorServiceHandler())
        pid = create_handler(PIDServiceHandler(metax))
        keystone = create_handler(KeystoneServiceHandler())
        auth = create_handler(AuthServiceHandler())
        file_provider = S3AllasFileProviderService()

        return DeploymentServices(
            project=project,
            file_provider=file_provider,
            metax=metax,
            ror=ror,
            pid=pid,
            keystone=keystone,
            auth=auth,
        )


class NbisDeploymentProfile(DeploymentProfile):
    """NBIS deployment."""

    deployment = Deployment.NBIS
    default_port = 5431
    submission_endpoints = False
    api_key_endpoints = False
    bucket_endpoints = False
    login_endpoints = False
    sda_ingest = True
    import_endpoints = True

    @override
    def create_services(
        self, create_handler: CreateHandler, object_service: ObjectService, file_service: FileService
    ) -> DeploymentServices:
        project = NbisProjectService()
        datacite = create_handler(DataciteServiceHandler(None))
        admin = create_handler(AdminServiceHandler())
        license_provider = BigpictureRemsLicenseProvider(object_service)
        sync_provider = BigpictureSyncMetadataProvider(object_service, file_service)
        file_provider = S3InboxSDAService(admin, Crypt4GHPublicKeyProvider(read_bp_public_key))

        return DeploymentServices(
            project=project,
            file_provider=file_provider,
            datacite=datacite,
            admin=admin,
            license_provider=license_provider,
            sync_provider=sync_provider,
        )


_PROFILES: dict[Deployment, DeploymentProfile] = {
    profile.deployment: profile for profile in (CscDeploymentProfile(), NbisDeploymentProfile())
}


def deployment_profile() -> DeploymentProfile:
    """
    Get the profile of the configured deployment.

    :returns: The deployment profile.
    """
    return _PROFILES[deployment_config().DEPLOYMENT]
