"""Metadata object models to inject accessions."""

from pydantic import BaseModel


class ObjectIdentifier(BaseModel):
    """Metadata object identifier with name and id."""

    schema_type: str
    object_type: str
    name: str
    id: str | None
    root_path: str  # Absolute path (e.g. XPath) to the metadata object root element.
