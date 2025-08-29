"""Postgres models."""

# pylint:skip-file

import enum
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Type

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Dialect,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import DeclarativeBase, Mapped, Relationship, backref, mapped_column, relationship
from sqlalchemy.sql.type_api import TypeEngine, UserDefinedType

from metadata_backend.api.models import ChecksumType, SubmissionWorkflow
from metadata_backend.api.services.accession import generate_default_accession


class TypeJSON(TypeDecorator[dict[str, Any]]):
    """
    Use PostgreSQL JSONB if available, otherwise fallback to JSON.

    Compatible with both Postgres and SQLite.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[dict[str, Any]]:
        """Override."""

        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class PostgresXML(UserDefinedType[str]):
    """Use PostgreSQL XMLType."""

    def get_col_spec(self, **kwargs: object) -> str:
        """Override."""
        return "XML"

    def bind_processor(self, dialect: Dialect) -> Optional[Callable[[Optional[str]], Optional[str]]]:
        """Override."""

        def process(value: Optional[str]) -> Optional[str]:
            return value

        return process

    def result_processor(self, dialect: Dialect, _: object) -> Optional[Callable[[Optional[str]], Optional[str]]]:
        """Override."""

        def process(value: Optional[str]) -> Optional[str]:
            return value

        return process


class TypeXML(TypeDecorator[str]):
    """
    Use PostgreSQL XML type if available, otherwise fallback to Text.

    Compatible with both Postgres and SQLite.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[str]:
        """Override."""

        if dialect.name == "postgresql":
            return dialect.type_descriptor(PostgresXML())
        else:
            return dialect.type_descriptor(Text())


def string_enum(enum_type: Type[enum.Enum]) -> Enum:
    """
    Store enum as string.

    :param enum_type: Enum type to store as string.
    :return: SQLAlchemy Enum type that stores enum values as strings.
    """
    return Enum(enum_type, native_enum=False, values_callable=lambda t: [item.value for item in t])


class Base(DeclarativeBase):
    """Base model for all tables."""


class ApiKeyEntity(Base):
    """Table for API keys."""

    __tablename__ = "api_keys"
    __table_args__ = (UniqueConstraint("user_id", "user_key_id"),)

    key_id: Mapped[str] = mapped_column(String, primary_key=True)  # Generated unique key id.
    user_id: Mapped[str] = mapped_column(String, nullable=False)  # User id.
    user_key_id: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)  # User's key id.
    api_key: Mapped[str] = mapped_column(String, nullable=False)  # Hashed API key.
    salt: Mapped[str] = mapped_column(String, nullable=False)  # Salt used to hash the API Key.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class SubmissionEntity(Base):
    """Table for submissions."""

    __tablename__ = "submissions"

    submission_id: Mapped[str] = mapped_column(String(128), primary_key=True, default=generate_default_accession)
    name: Mapped[str] = mapped_column(String, nullable=False)  # User provided name for the submission
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    folder: Mapped[str] = mapped_column(String(64), nullable=True)  # Could this be nullable?
    workflow: Mapped[SubmissionWorkflow] = mapped_column(string_enum(SubmissionWorkflow), nullable=False)

    title: Mapped[str] = mapped_column(String, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    modified: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )

    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_ingested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    published: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(TypeJSON), nullable=False)


@event.listens_for(SubmissionEntity.is_published, "set")
def set_date_published(target: SubmissionEntity, value: bool, old_value: bool, _: object) -> None:
    """Automatically set published date in application."""

    if value is True and old_value is False:
        target.published = datetime.now(timezone.utc)


@event.listens_for(SubmissionEntity.is_ingested, "set")
def set_date_ingested(target: SubmissionEntity, value: bool, old_value: bool, _: object) -> None:
    """Automatically set ingested date in application."""

    if value is True and old_value is False:
        target.ingested = datetime.now(timezone.utc)


class ObjectEntity(Base):
    """Table for submitted metadata objects."""

    __tablename__ = "objects"

    object_id: Mapped[str] = mapped_column(String(128), primary_key=True, default=generate_default_accession)
    name: Mapped[str] = mapped_column(String, nullable=True)  # User provided name for the object
    schema: Mapped[str] = mapped_column(String, nullable=False)
    submission_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("submissions.submission_id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    document: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(TypeJSON), nullable=True)
    xml_document: Mapped[str] = mapped_column(TypeXML, nullable=True)

    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    modified: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )

    submission: Mapped[Relationship[SubmissionEntity]] = relationship(
        SubmissionEntity,
        backref=backref(
            "objects",
            cascade="all, delete-orphan",  # tell ORM that database does on delete cascade
            passive_deletes=True,  # tell ORM that database does on delete cascade
            single_parent=True,
        ),
        passive_deletes=True,  # safe here if ON DELETE CASCADE is set in FK
    )


class IngestStatus(enum.Enum):
    """File ingest status."""

    ADDED = "added"
    READY = "ready"
    VERIFIED = "verified"
    COMPLETED = "completed"
    FAILED = "failed"


class FileEntity(Base):
    """Table for submitted files."""

    __tablename__ = "files"
    __table_args__ = (UniqueConstraint("submission_id", "path"),)

    file_id: Mapped[str] = mapped_column(String(128), primary_key=True, default=generate_default_accession)
    submission_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("submissions.submission_id", ondelete="CASCADE"), nullable=False, index=True
    )
    object_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("objects.object_id", ondelete="CASCADE"), nullable=True, index=True
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, nullable=True)

    unencrypted_checksum: Mapped[str] = mapped_column(String(128), nullable=True)
    unencrypted_checksum_type: Mapped[ChecksumType] = mapped_column(string_enum(ChecksumType), nullable=True)
    encrypted_checksum: Mapped[str] = mapped_column(String(128), nullable=True)
    encrypted_checksum_type: Mapped[ChecksumType] = mapped_column(string_enum(ChecksumType), nullable=True)

    ingest_status: Mapped[IngestStatus] = mapped_column(
        string_enum(IngestStatus), nullable=False, default=IngestStatus.ADDED, index=True
    )
    ingest_error: Mapped[str | None] = mapped_column(String, nullable=True)

    submission: Mapped[Relationship[SubmissionEntity]] = relationship(
        SubmissionEntity,
        backref=backref(
            "files",
            cascade="all, delete-orphan",  # tell ORM that database does on delete cascade
            passive_deletes=True,  # tell ORM that database does on delete cascade
            single_parent=True,
        ),
        passive_deletes=True,  # safe here if ON DELETE CASCADE is set in FK
    )

    object: Mapped[Relationship[ObjectEntity]] = relationship(
        ObjectEntity,
        backref=backref(
            "files",
            cascade="all, delete-orphan",  # tell ORM that database does on delete cascade
            passive_deletes=True,  # tell ORM that database does on delete cascade
            single_parent=True,
        ),
        passive_deletes=True,  # safe here if ON DELETE CASCADE is set in FK
    )


class RegistrationEntity(Base):
    """Table for registrations."""

    __tablename__ = "registrations"

    registration_id: Mapped[str] = mapped_column(String(128), primary_key=True, default=generate_default_accession)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    schema: Mapped[str] = mapped_column(String(256), nullable=True)
    doi: Mapped[str] = mapped_column(String(256), nullable=False, comment="Digital Object identifier")
    metax_id: Mapped[str] = mapped_column(String(256), nullable=True, comment="Metax identifier")
    datacite_url: Mapped[str] = mapped_column(String(1024), nullable=True, comment="Datacite discovery URL")
    rems_url = mapped_column(String, nullable=True)
    rems_resource_id = mapped_column(String, nullable=True)
    rems_catalogue_id = mapped_column(String, nullable=True)

    submission_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("submissions.submission_id", ondelete="CASCADE"), nullable=False, index=True
    )
    object_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("objects.object_id", ondelete="CASCADE"), nullable=True, index=True, unique=True
    )

    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    modified: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )

    submission: Mapped[Relationship[SubmissionEntity]] = relationship(
        SubmissionEntity,
        backref=backref(
            "registrations",
            cascade="all, delete-orphan",  # tell ORM that database does on delete cascade
            passive_deletes=True,  # tell ORM that database does on delete cascade
            single_parent=True,
        ),
        passive_deletes=True,  # safe here if ON DELETE CASCADE is set in FK
    )

    object: Mapped[Relationship[ObjectEntity]] = relationship(
        ObjectEntity,
        backref=backref(
            "registrations",
            cascade="all, delete-orphan",  # tell ORM that database does on delete cascade
            passive_deletes=True,  # tell ORM that database does on delete cascade
            single_parent=True,
        ),
        passive_deletes=True,  # safe here if ON DELETE CASCADE is set in FK
    )
