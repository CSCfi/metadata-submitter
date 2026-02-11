"""Postgres models."""

import enum
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Type

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
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
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import DeclarativeBase, Mapped, Relationship, backref, mapped_column, relationship
from sqlalchemy.sql.type_api import TypeEngine, UserDefinedType

from ...api.models.models import CHECKSUM_METHOD_TYPES
from ...api.models.submission import SubmissionWorkflow

SUBMISSIONS_TABLE = "submissions"
OBJECTS_TABLE = "objects"
FILES_TABLE = "files"
REGISTRATIONS_TABLE = "registrations"


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

    def get_col_spec(self, **_kwargs: object) -> str:
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
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),  # For SQLLite
        nullable=False,
    )


class SubmissionEntity(Base):
    """Table for submissions."""

    __tablename__ = SUBMISSIONS_TABLE
    __table_args__ = (
        CheckConstraint(
            f"workflow IN ({', '.join(repr(e.value) for e in SubmissionWorkflow)})",
            name="ck_workflow",
        ),
    )

    submission_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)  # User provided name for the submission
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    bucket: Mapped[str] = mapped_column(String(64), nullable=True)  # Could this be nullable?
    workflow: Mapped[SubmissionWorkflow] = mapped_column(string_enum(SubmissionWorkflow), nullable=False)

    title: Mapped[str] = mapped_column(String, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),  # For SQLLite
        index=True,
    )
    modified: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),  # For SQLLite
        server_onupdate=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),  # For SQLLite
        index=True,
    )

    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false(), index=True)
    is_ingested: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false(), index=True)
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

    __tablename__ = OBJECTS_TABLE

    object_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=True)  # User provided name for the object
    object_type: Mapped[str] = mapped_column(String, nullable=False)
    submission_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("submissions.submission_id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(String, nullable=False)

    title: Mapped[str] = mapped_column(String, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    document: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(TypeJSON), nullable=True)
    xml_document: Mapped[str] = mapped_column(TypeXML, nullable=True)

    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),  # For SQLLite
        index=True,
    )
    modified: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),  # For SQLLite
        server_onupdate=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),  # For SQLLite
        index=True,
    )

    submission: Mapped[Relationship[SubmissionEntity]] = relationship(
        SubmissionEntity,
        backref=backref(
            OBJECTS_TABLE,
            cascade="all, delete-orphan",  # tell ORM that database does on delete cascade
            passive_deletes=True,  # tell ORM that database does on delete cascade
            single_parent=True,
        ),
        passive_deletes=True,  # safe here if ON DELETE CASCADE is set in FK
    )


class IngestStatus(enum.Enum):
    """File ingest status."""

    # The file ingestion statuses are a subset of those defined in NeIC SDA.
    SUBMITTED = "submitted"  # The file has been submitted and can be ingested once the submission has been published.
    VERIFIED = "verified"  # File checksums have been verified.
    READY = "ready"  # The file ingestion has completed.
    ERROR = "error"  # The file ingestion has failed.


class IngestErrorType(enum.Enum):
    """File ingest error type."""

    USER_ERROR = "user_error"
    TRANSIENT_ERROR = "transient_error"
    PERMANENT_ERROR = "permanent_error"


class FileEntity(Base):
    """Table for submitted files."""

    __tablename__ = FILES_TABLE
    __table_args__ = (
        UniqueConstraint("submission_id", "path"),
        CheckConstraint(
            f"checksum_method IN ({', '.join(repr(e) for e in CHECKSUM_METHOD_TYPES)})",
            name="ck_checksum_method",
        ),
        CheckConstraint(
            f"ingest_status IN ({', '.join(repr(e.value) for e in IngestStatus)})",
            name="ck_ingest_status",
        ),
        CheckConstraint(
            f"ingest_error_type IN ({', '.join(repr(e.value) for e in IngestErrorType)})",
            name="ck_ingest_error_type",
        ),
    )

    file_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    submission_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("submissions.submission_id", ondelete="CASCADE"), nullable=False, index=True
    )
    object_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("objects.object_id", ondelete="CASCADE"), nullable=True, index=True
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    bytes: Mapped[int] = mapped_column(BigInteger, nullable=True)

    checksum_method: Mapped[str] = mapped_column(String(16), nullable=True)
    unencrypted_checksum: Mapped[str] = mapped_column(String(128), nullable=True)
    encrypted_checksum: Mapped[str] = mapped_column(String(128), nullable=True)

    ingest_status: Mapped[IngestStatus] = mapped_column(
        string_enum(IngestStatus), nullable=False, server_default=text(f"'{IngestStatus.SUBMITTED.value}'"), index=True
    )
    ingest_error: Mapped[str | None] = mapped_column(String, nullable=True)
    ingest_error_type: Mapped[IngestErrorType | None] = mapped_column(string_enum(IngestErrorType), nullable=True)
    ingest_error_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),  # For SQLLite
        index=True,
    )
    modified: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),  # For SQLLite
        server_onupdate=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),  # For SQLLite
        index=True,
    )

    submission: Mapped[Relationship[SubmissionEntity]] = relationship(
        SubmissionEntity,
        backref=backref(
            FILES_TABLE,
            cascade="all, delete-orphan",  # tell ORM that database does on delete cascade
            passive_deletes=True,  # tell ORM that database does on delete cascade
            single_parent=True,
        ),
        passive_deletes=True,  # safe here if ON DELETE CASCADE is set in FK
    )

    object: Mapped[Relationship[ObjectEntity]] = relationship(
        ObjectEntity,
        backref=backref(
            FILES_TABLE,
            cascade="all, delete-orphan",  # tell ORM that database does on delete cascade
            passive_deletes=True,  # tell ORM that database does on delete cascade
            single_parent=True,
        ),
        passive_deletes=True,  # safe here if ON DELETE CASCADE is set in FK
    )


class RegistrationEntity(Base):
    """Table for registrations."""

    __tablename__ = REGISTRATIONS_TABLE

    submission_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("submissions.submission_id", ondelete="CASCADE"), primary_key=True
    )
    object_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("objects.object_id", ondelete="CASCADE"), nullable=True, index=True, unique=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    object_type: Mapped[str] = mapped_column(String(256), nullable=True)
    doi: Mapped[str] = mapped_column(String(256), nullable=False, comment="Digital Object identifier")
    metax_id: Mapped[str] = mapped_column(String(256), nullable=True, comment="Metax identifier")
    datacite_url: Mapped[str] = mapped_column(String(1024), nullable=True, comment="Datacite discovery URL")
    rems_url = mapped_column(String, nullable=True)
    rems_resource_id = mapped_column(String, nullable=True)
    rems_catalogue_id = mapped_column(String, nullable=True)

    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),  # For SQLLite
        index=True,
    )
    modified: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),  # For SQLLite
        server_onupdate=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),  # For SQLLite
        index=True,
    )

    submission: Mapped[Relationship[SubmissionEntity]] = relationship(
        SubmissionEntity,
        backref=backref(
            REGISTRATIONS_TABLE,
            cascade="all, delete-orphan",  # tell ORM that database does on delete cascade
            passive_deletes=True,  # tell ORM that database does on delete cascade
            single_parent=True,
        ),
        passive_deletes=True,  # safe here if ON DELETE CASCADE is set in FK
    )

    object: Mapped[Relationship[ObjectEntity]] = relationship(
        ObjectEntity,
        backref=backref(
            REGISTRATIONS_TABLE,
            cascade="all, delete-orphan",  # tell ORM that database does on delete cascade
            passive_deletes=True,  # tell ORM that database does on delete cascade
            single_parent=True,
        ),
        passive_deletes=True,  # safe here if ON DELETE CASCADE is set in FK
    )
