"""Replace the object document columns with a single object column.

The metadata object is stored either as plain UTF-8, or encrypted using
direct or envelope encryption. The stored bytes will determine which.
Metadata objects created before this migration are all unencrypted.

Metadata object are encrypted during the migration if OPENBAO_URL environment
variable is defined.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable

import sqlalchemy as sa
from alembic import op

from metadata_backend.api.services.openbao import OpenBaoService
from metadata_backend.conf.openbao import openbao_config
from metadata_backend.database.postgres.services.object import decode_object, encode_object

revision = "20260917_01"
down_revision = "20260520_01"
branch_labels = None
depends_on = None


_TABLE = "objects"

# How many objects are read into memory at a time during migration.
_BATCH = 500


@asynccontextmanager
async def _openbao() -> AsyncIterator[OpenBaoService | None]:
    """The OpenBao service if the OPENBAO_URL environment variable is defined."""

    service = OpenBaoService() if openbao_config().OPENBAO_URL else None
    try:
        yield service
    finally:
        if service is not None:
            await service.close()


async def _encode_objects() -> None:
    """Move the XML documents into the object column, encrypting them if OpenBao is configured."""

    async with _openbao() as openbao:
        if openbao is not None:
            # Check the encryption key.
            await openbao.validate()
        await _convert("CAST(xml_document AS text)", "object", lambda document: encode_object(document, openbao))


async def _decode_objects() -> None:
    """Move the objects back into the XML document column, decrypting the encrypted ones."""

    async with _openbao() as openbao:
        await _convert("object", "xml_document", lambda data: decode_object(data, openbao))


def _columns() -> set[str]:
    """Return the columns of the objects table, or nothing if the table does not exist."""

    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(_TABLE)}


async def _convert(read_column: str, write_column: str, convert: Callable[[Any], Awaitable[Any]]) -> None:
    """
    Convert every object from one column into the other, a batch at a time.

    :param read_column: The column the objects are read from.
    :param write_column: The column the objects are written to.
    :param convert: The conversion applied to each object.
    """

    bind = op.get_bind()
    last_object_id = ""

    while True:
        rows = bind.execute(
            sa.text(
                f"SELECT object_id, {read_column} AS value FROM {_TABLE} "
                "WHERE object_id > :last ORDER BY object_id LIMIT :limit"
            ),
            {"last": last_object_id, "limit": _BATCH},
        ).fetchall()

        if not rows:
            return

        updates = [
            {"object_id": object_id, "value": await convert(value)} for object_id, value in rows if value is not None
        ]
        if updates:
            bind.execute(
                sa.text(f"UPDATE {_TABLE} SET {write_column} = :value WHERE object_id = :object_id"),
                updates,
            )

        last_object_id = rows[-1][0]


def upgrade() -> None:
    columns = _columns()
    if not columns:
        return

    if "object" not in columns:
        op.add_column(_TABLE, sa.Column("object", sa.LargeBinary(), nullable=True))

    if "xml_document" in columns:
        # Migrate the XML documents into the new column. Every object has an XML document.
        asyncio.run(_encode_objects())
        op.drop_column(_TABLE, "xml_document")

    op.alter_column(_TABLE, "object", existing_type=sa.LargeBinary(), nullable=False)

    if "document" in columns:
        # No JSON documents to migrate.
        op.drop_column(_TABLE, "document")


def downgrade() -> None:
    columns = _columns()
    if not columns:
        return

    if "document" not in columns:
        op.execute(sa.text(f"ALTER TABLE {_TABLE} ADD COLUMN document JSONB"))

    if "xml_document" not in columns:
        op.execute(sa.text(f"ALTER TABLE {_TABLE} ADD COLUMN xml_document XML"))
        asyncio.run(_decode_objects())

    if "object" in columns:
        op.drop_column(_TABLE, "object")
