"""NeIC SDA Admin API request models."""

from datetime import datetime

from pydantic import UUID4, BaseModel, Field, RootModel


class FileItem(BaseModel):
    file_id: UUID4 = Field(..., alias="fileID")
    inbox_path: str = Field(..., alias="inboxPath")
    file_status: str = Field(..., alias="fileStatus")
    created_at: datetime = Field(..., alias="createAt")


class UserFilesResponse(RootModel[list[FileItem]]):
    """Admin API response model for listing inbox files."""


class IngestFileRequest(BaseModel):
    """Request payload for starting file ingestion."""

    user: str
    filepath: str


class PostAccessionIdRequest(BaseModel):
    """Request payload for assigning accession id to a file."""

    accession_id: str
    filepath: str
    user: str


class CreateDatasetRequest(BaseModel):
    """Request payload for dataset creation."""

    accession_ids: list[str]
    dataset_id: str
    user: str
