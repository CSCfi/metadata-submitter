"""Postgres models."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base model for all tables."""


class ApiKeyEntity(Base):
    """Model for the API keys."""

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
