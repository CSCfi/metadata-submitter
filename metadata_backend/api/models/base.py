from pydantic import BaseModel


class StrictBaseModel(BaseModel):
    """A base model that disallows extra fields."""

    model_config = {"extra": "forbid"}
