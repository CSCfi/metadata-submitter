"""Shared resources."""

from enum import Enum
from typing import Any, cast

from aiohttp.web import AppKey, Application, Request

from ..database.postgres.services.file import FileService
from ..database.postgres.services.object import ObjectService
from ..database.postgres.services.registration import RegistrationService
from ..database.postgres.services.submission import SubmissionService
from .services.auth import AccessService
from .services.file import FileProviderService
from .services.object import JsonObjectService, XmlObjectService
from .services.project import ProjectService


class ResourceType(Enum):
    """Resource types for the application context."""

    PROJECT_SERVICE = "project_service"
    ACCESS_SERVICE = "access_service"
    SUBMISSION_SERVICE = "submission_service"
    OBJECT_SERVICE = "object_service"
    FILE_SERVICE = "file_service"
    REGISTRATION_SERVICE = "registration_service"
    JSON_OBJECT_SERVICE = "json_object_service"
    XML_OBJECT_SERVICE = "xml_object_service"
    FILE_PROVIDER_SERVICE = "file_provider_service"


# Map ResourceType to AppKey instances according to:
# https://docs.aiohttp.org/en/stable/web_advanced.html#application-s-config
APP_KEYS: dict[ResourceType, AppKey[Any]] = {
    ResourceType.PROJECT_SERVICE: AppKey("project_service"),
    ResourceType.ACCESS_SERVICE: AppKey("access_service"),
    ResourceType.SUBMISSION_SERVICE: AppKey("submission_service"),
    ResourceType.OBJECT_SERVICE: AppKey("object_service"),
    ResourceType.FILE_SERVICE: AppKey("file_service"),
    ResourceType.REGISTRATION_SERVICE: AppKey("registration_service"),
    ResourceType.JSON_OBJECT_SERVICE: AppKey("json_object_service"),
    ResourceType.XML_OBJECT_SERVICE: AppKey("xml_object_service"),
    ResourceType.FILE_PROVIDER_SERVICE: AppKey("file_provider_service"),
}


def set_resource(app: Application, resource_type: ResourceType, resource: Any) -> None:  # noqa: ANN401
    """
    Attach the resource to the application.

    Args:
        app: The application context.
        resource_type: the resource type.
        resource: the resource.
    """
    app[APP_KEYS[resource_type]] = resource


def get_access_service(req: Request) -> AccessService:
    """
    Retrieve the AccessService from the application.

    Args:
        req: The incoming HTTP request containing the application context.

    Returns:
        AccessService: The AccessService attached to the application.
    """
    return cast(AccessService, req.app[APP_KEYS[ResourceType.ACCESS_SERVICE]])


def get_project_service(req: Request) -> ProjectService:
    """
    Retrieve the ProjectService from the application.

    Args:
        req: The incoming HTTP request containing the application context.

    Returns:
        ProjectService: The ProjectService attached to the application.
    """
    return cast(ProjectService, req.app[APP_KEYS[ResourceType.PROJECT_SERVICE]])


def get_submission_service(req: Request) -> SubmissionService:
    """
    Retrieve the Postgres SubmissionService from the application.

    Args:
        req: The incoming HTTP request containing the application context.

    Returns:
        SubmissionService: The Postgres SubmissionService attached to the application.
    """
    return cast(SubmissionService, req.app[APP_KEYS[ResourceType.SUBMISSION_SERVICE]])


def get_object_service(req: Request) -> ObjectService:
    """
    Retrieve the Postgres ObjectService from the application.

    Args:
        req: The incoming HTTP request containing the application context.

    Returns:
        ObjectService: The Postgres ObjectService attached to the application.
    """
    return cast(ObjectService, req.app[APP_KEYS[ResourceType.OBJECT_SERVICE]])


def get_file_service(req: Request) -> FileService:
    """
    Retrieve the Postgres FileService from the application.

    Args:
        req: The incoming HTTP request containing the application context.

    Returns:
        FileService: The Postgres FileService attached to the application.
    """
    return cast(FileService, req.app[APP_KEYS[ResourceType.FILE_SERVICE]])


def get_registration_service(req: Request) -> RegistrationService:
    """
    Retrieve the Postgres RegistrationService from the application.

    Args:
        req: The incoming HTTP request containing the application context.

    Returns:
        RegistrationService: The Postgres RegistrationService attached to the application.
    """
    return cast(RegistrationService, req.app[APP_KEYS[ResourceType.REGISTRATION_SERVICE]])


def get_json_object_service(req: Request) -> JsonObjectService:
    """
    Retrieve the JSonObjectService from the application.

    Args:
        req: The incoming HTTP request containing the application context.

    Returns:
        ObjectService: The JsonObjectService attached to the application.
    """
    return cast(JsonObjectService, req.app[APP_KEYS[ResourceType.JSON_OBJECT_SERVICE]])


def get_xml_object_service(req: Request) -> XmlObjectService:
    """
    Retrieve the XmlObjectService from the application.

    Args:
        req: The incoming HTTP request containing the application context.

    Returns:
        XmlObjectService: The XmlObjectService attached to the application.
    """
    return cast(XmlObjectService, req.app[APP_KEYS[ResourceType.XML_OBJECT_SERVICE]])


def get_file_provider_service(req: Request) -> FileProviderService:
    """
    Retrieve the FileProviderService from the application.

    Args:
        req: The incoming HTTP request containing the application context.

    Returns:
        FileProviderService: The FileProviderService attached to the application.
    """
    return cast(FileProviderService, req.app[APP_KEYS[ResourceType.FILE_PROVIDER_SERVICE]])
