"""Submission models."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional, Type

from pydantic import ValidationInfo, model_validator

from .base import StrictBaseModel
from .datacite import DataCiteMetadata


class SubmissionWorkflow(enum.Enum):
    """Submission workflow."""

    SD = "SD"
    FEGA = "FEGA"
    BP = "Bigpicture"

    @classmethod
    def _missing_(cls: Type["SubmissionWorkflow"], value: object) -> "SubmissionWorkflow":
        """Map enumeration value aliases."""

        if value in ("SDS", "SDSX"):
            return cls.SD
        raise ValueError(f"{value!r} is not a valid {cls.__name__}")


class Bucket(StrictBaseModel):
    """`Bucket information."""

    bucket: str


class Rems(StrictBaseModel):
    """REMS information."""

    workflowId: int
    organizationId: str | None = None  # If given then validate against workflow id.
    licenses: list[int] | None = None


class SubmissionMetadata(DataCiteMetadata):
    """Submission metadata."""

    keywords: Optional[str] = None  # Metax keywords ## TODO(improve): make a list

    def to_datacite(self) -> DataCiteMetadata:
        """Convert to datacite metadata while preserve types and excluding non-datacite fields."""
        return DataCiteMetadata.model_validate(
            {k: v for k, v in self.model_dump().items() if k in DataCiteMetadata.model_fields.keys()}
        )

    def update_datacite(self, datacite: DataCiteMetadata) -> None:
        """
        Update datacite metadata in the submission metadata.

        :param datacite: the new datacite metadata.
        """
        for k in DataCiteMetadata.model_fields.keys():
            setattr(self, k, getattr(datacite, k))

    @staticmethod
    def from_datacite(datacite: DataCiteMetadata) -> SubmissionMetadata:
        """
        Create a submission metadata from dataCite metadata.

        :param datacite: The datacite metadata
        :return: The submission metadata.
        """
        return SubmissionMetadata(**{k: getattr(datacite, k) for k in DataCiteMetadata.model_fields.keys()})


class Submission(StrictBaseModel):
    """Submission document."""

    projectId: str
    submissionId: str | None = None  # Stored only in a database column.
    name: str
    title: str
    description: str
    workflow: SubmissionWorkflow | None = None
    bucket: str | None = None  # Stored only in a database column.
    metadata: SubmissionMetadata | None = None
    rems: Rems | None = None
    dateCreated: datetime | None = None  # Stored only in a database column.
    datePublished: datetime | None = None  # Stored only in a database column.
    lastModified: datetime | None = None  # Stored only in a database column.
    published: bool | None = None  # Stored only in a database column.

    @model_validator(mode="before")
    @classmethod
    def model_validator_context(cls: type["Submission"], values: dict, info: ValidationInfo) -> dict:  # type: ignore
        if info.context and info.context.get("projectId"):
            values["projectId"] = info.context.get("projectId")
        if info.context and info.context.get("workflow"):
            values["workflow"] = info.context.get("workflow")
        return values


class Submissions(StrictBaseModel):
    """Submission documents."""

    submissions: list[Submission]


class PaginatedSubmissionsPage(StrictBaseModel):
    """Paginated submission documents page."""

    page: int
    size: int
    totalPages: int
    totalSubmissions: int


class PaginatedSubmissions(StrictBaseModel):
    """Paginated submission documents."""

    page: PaginatedSubmissionsPage
    submissions: list[Submission]
