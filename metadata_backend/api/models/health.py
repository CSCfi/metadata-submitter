"""Health models."""

from enum import Enum

from pydantic import BaseModel


class Health(str, Enum):
    """Health status."""

    UP = "Up"
    DOWN = "Down"
    DEGRADED = "Degraded"
    ERROR = "Error"


class ServiceHealth(BaseModel):
    """Service health."""

    status: Health
    services: dict[str, Health]
