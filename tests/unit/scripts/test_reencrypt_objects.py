"""Test re-encrypting the stored metadata objects."""

import uuid

import pytest
from sqlalchemy import text

from metadata_backend.api.exceptions import SystemException
from metadata_backend.api.services.openbao import _DIRECT_KIND, _ENVELOPE_KIND, SD_SUBMIT_MAGIC
from metadata_backend.conf.openbao import DIRECT, ENVELOPE
from metadata_backend.database.postgres.models import ObjectEntity, SubmissionEntity
from metadata_backend.database.postgres.repository import create_engine, create_session_factory, get_sqllite_db_url
from metadata_backend.database.postgres.services.object import decode_object, is_encrypted
from metadata_backend.scripts import reencrypt_objects
from metadata_backend.scripts.reencrypt_objects import main
from tests.unit.openbao import MockOpenBaoService

DOCUMENT = '<TEST alias="1"><VALUE>test</VALUE></TEST>'


def _kind(obj: bytes) -> int:
    """Return the byte saying how a stored object was encrypted."""

    return obj[len(SD_SUBMIT_MAGIC)]


def set_openbao_env(monkeypatch, openbao: MockOpenBaoService) -> None:
    monkeypatch.setenv("OPENBAO_URL", "http://openbao:8200")
    monkeypatch.setenv("OPENBAO_TOKEN", "test-token")
    monkeypatch.setenv("OPENBAO_OBJECT_KEY_NAME", "test-key")
    monkeypatch.setattr(reencrypt_objects, "OpenBaoService", lambda: openbao)


@pytest.fixture
async def database(monkeypatch, tmp_path):
    """A database of the script's own, so it commits without the session fixture's transaction."""

    monkeypatch.setenv("DATABASE_URL", get_sqllite_db_url(str(tmp_path / "reencrypt.db")))
    engine = await create_engine()
    try:
        yield create_session_factory(engine)
    finally:
        await engine.dispose()


async def _add_objects(session_factory, objects: list[bytes]) -> list[str]:
    """Store the given objects as they are, and return their object ids."""

    submission = SubmissionEntity(
        submission_id=f"submission_{uuid.uuid4()}",
        name="test",
        project_id="test",
        workflow="Bigpicture",
        document={},
    )
    entities = [
        ObjectEntity(
            object_id=f"object_{uuid.uuid4()}",
            name=f"name_{uuid.uuid4()}",
            object_type="test",
            submission_id=submission.submission_id,
            project_id="test",
            object=obj,
        )
        for obj in objects
    ]

    async with session_factory() as session, session.begin():
        session.add(submission)
        session.add_all(entities)

    return [entity.object_id for entity in entities]


async def _read_objects(session_factory, object_ids: list[str]) -> list[bytes]:
    """Read the stored objects as they are, without decoding them."""

    async with session_factory() as session:
        result = await session.execute(text("SELECT object_id, object FROM objects"))
        stored = {object_id: bytes(obj) for object_id, obj in result}

    return [stored[object_id] for object_id in object_ids]


async def test_objects_are_encrypted(database, monkeypatch) -> None:
    openbao = MockOpenBaoService()
    object_ids = await _add_objects(database, [DOCUMENT.encode("utf-8")])

    set_openbao_env(monkeypatch, openbao)
    await main()

    for obj in await _read_objects(database, object_ids):
        assert is_encrypted(obj)
        assert await decode_object(obj, openbao) == DOCUMENT


async def test_objects_are_re_encrypted(database, monkeypatch) -> None:
    openbao = MockOpenBaoService(ENVELOPE, asymmetric=False)
    written = await openbao.encrypt_direct(DOCUMENT)
    assert _kind(written) == _DIRECT_KIND

    object_ids = await _add_objects(database, [written])

    set_openbao_env(monkeypatch, openbao)
    await main()

    for obj in await _read_objects(database, object_ids):
        assert _kind(obj) == _ENVELOPE_KIND
        assert await decode_object(obj, openbao) == DOCUMENT


async def test_invalid_key_fails_before_any_object(database, monkeypatch) -> None:
    # Attempt to use an asymmetric key for direct encryption.
    openbao = MockOpenBaoService(DIRECT, asymmetric=True)
    object_ids = await _add_objects(database, [DOCUMENT.encode("utf-8")])

    set_openbao_env(monkeypatch, openbao)
    # Re-encryption should fail because direct encryption requires a symmetric key.
    with pytest.raises(SystemException, match="requires a symmetric"):
        await main()

    assert await _read_objects(database, object_ids) == [DOCUMENT.encode("utf-8")]
