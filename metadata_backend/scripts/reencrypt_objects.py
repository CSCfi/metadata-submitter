#!/usr/bin/env python3
"""
Re-encrypt every stored metadata object. Encrypts objects using the encoding and key
defined by the OPENBAO environmental variables.

    python -m metadata_backend.scripts.reencrypt_objects
"""

import asyncio

from sqlalchemy import text

from metadata_backend.api.services.openbao import OpenBaoService
from metadata_backend.conf.openbao import openbao_config
from metadata_backend.database.postgres.repository import create_engine, create_session_factory
from metadata_backend.database.postgres.services.object import decode_object, encode_object
from metadata_backend.helpers.logger import LOG

# How many objects are read into memory at a time.
BATCH = 500


async def main() -> None:
    """Re-encrypt every stored metadata object."""

    openbao = OpenBaoService() if openbao_config().OPENBAO_URL else None

    try:
        if openbao is not None:
            # Check the encryption key before any objects are encrypted or decrypted.
            await openbao.validate()

        engine = await create_engine()
        session_factory = create_session_factory(engine)

        last_object_id = ""
        total = 0

        try:
            while True:
                async with session_factory() as session, session.begin():
                    rows = (
                        await session.execute(
                            text(
                                "SELECT object_id, object FROM objects "
                                "WHERE object_id > :last "
                                "ORDER BY object_id LIMIT :limit"
                            ),
                            {"last": last_object_id, "limit": BATCH},
                        )
                    ).fetchall()

                    if not rows:
                        break

                    updates = [
                        {
                            "object_id": object_id,
                            "object": await encode_object(await decode_object(obj, openbao), openbao),
                        }
                        for object_id, obj in rows
                    ]
                    await session.execute(
                        text("UPDATE objects SET object = :object WHERE object_id = :object_id"),
                        updates,
                    )

                    last_object_id = rows[-1][0]
                    total += len(rows)
                    LOG.info("Re-encrypted %d metadata objects.", total)
        finally:
            await engine.dispose()
    finally:
        if openbao is not None:
            await openbao.close()

    LOG.info("Re-encrypted %d metadata objects in total.", total)


if __name__ == "__main__":
    asyncio.run(main())
