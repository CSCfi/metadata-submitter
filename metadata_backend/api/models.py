"""API models."""

from datetime import datetime

from pydantic import BaseModel


class ApiKey(BaseModel):
    """Represents a user API key."""

    key_id: str
    created_at: datetime | None = None


class User(BaseModel):
    """Represents a user."""

    user_id: str
    user_name: str
    projects: list["Project"] = []


class Project(BaseModel):
    """Represents a user project."""

    project_id: str
