from metadata_backend.database.postgres.repositories.dispatch import DispatchRepository
from metadata_backend.database.postgres.repositories.submission import SubmissionRepository
from tests.unit.database.postgres.helpers import create_submission_entity


async def add_submission(submission_repository: SubmissionRepository) -> str:
    return await submission_repository.add_submission(create_submission_entity())


async def test_mark_dispatched_with_and_without_target(
    dispatch_repository: DispatchRepository,
    submission_repository: SubmissionRepository,
) -> None:
    submission_id = await add_submission(submission_repository)

    await dispatch_repository.mark_dispatched(submission_id, "sda_admin", "dataset_create", "")
    await dispatch_repository.mark_dispatched(submission_id, "sda_admin", "file_ingest", "file-1")

    dispatches = await dispatch_repository.get_dispatches(submission_id, "sda_admin")
    keys = {(d.action, d.target) for d in dispatches}
    assert keys == {("dataset_create", ""), ("file_ingest", "file-1")}


async def test_mark_dispatched_inserts_then_updates(
    dispatch_repository: DispatchRepository,
    submission_repository: SubmissionRepository,
) -> None:
    submission_id = await add_submission(submission_repository)

    await dispatch_repository.mark_dispatched(submission_id, "sda_admin", "file_ingest", "file-1")
    dispatches = await dispatch_repository.get_dispatches(submission_id, "sda_admin")
    assert len(dispatches) == 1
    assert dispatches[0].attempts == 1
    assert dispatches[0].dispatched_at is not None

    # A second dispatch for the same (submission_id, service, action, target) key updates the
    # existing row rather than inserting a duplicate (which would violate the composite PK) --
    # this is also what catches a composite-PK column-order mistake in mark_dispatched.
    await dispatch_repository.mark_dispatched(submission_id, "sda_admin", "file_ingest", "file-1")
    dispatches = await dispatch_repository.get_dispatches(submission_id, "sda_admin")
    assert len(dispatches) == 1
    assert dispatches[0].attempts == 2


async def test_delete_dispatches_removes_only_that_service(
    dispatch_repository: DispatchRepository,
    submission_repository: SubmissionRepository,
) -> None:
    submission_id = await add_submission(submission_repository)

    await dispatch_repository.mark_dispatched(submission_id, "sda_admin", "file_ingest", "file-1")
    await dispatch_repository.mark_dispatched(submission_id, "other_service", "some_action", "")

    await dispatch_repository.delete_dispatches(submission_id, "sda_admin")

    assert await dispatch_repository.get_dispatches(submission_id, "sda_admin") == []
    other_dispatches = await dispatch_repository.get_dispatches(submission_id, "other_service")
    assert len(other_dispatches) == 1


async def test_submission_delete_cascades_to_dispatches(
    dispatch_repository: DispatchRepository,
    submission_repository: SubmissionRepository,
) -> None:
    submission_id = await add_submission(submission_repository)
    await dispatch_repository.mark_dispatched(submission_id, "sda_admin", "file_ingest", "file-1")

    assert await submission_repository.delete_submission_by_id(submission_id)

    assert await dispatch_repository.get_dispatches(submission_id, "sda_admin") == []


async def test_get_dispatches_does_not_leak_across_submissions(
    dispatch_repository: DispatchRepository,
    submission_repository: SubmissionRepository,
) -> None:
    """The composite PK starts with submission_id; a query must never return another submission's rows."""
    submission_id_1 = await add_submission(submission_repository)
    submission_id_2 = await add_submission(submission_repository)

    # Same service/action/target on two different submissions.
    await dispatch_repository.mark_dispatched(submission_id_1, "sda_admin", "file_ingest", "file-1")
    await dispatch_repository.mark_dispatched(submission_id_2, "sda_admin", "file_ingest", "file-1")

    dispatches_1 = await dispatch_repository.get_dispatches(submission_id_1, "sda_admin")
    dispatches_2 = await dispatch_repository.get_dispatches(submission_id_2, "sda_admin")
    assert {d.submission_id for d in dispatches_1} == {submission_id_1}
    assert {d.submission_id for d in dispatches_2} == {submission_id_2}

    # Deleting one submission's dispatches must not touch the other's.
    await dispatch_repository.delete_dispatches(submission_id_1, "sda_admin")
    assert await dispatch_repository.get_dispatches(submission_id_1, "sda_admin") == []
    assert len(await dispatch_repository.get_dispatches(submission_id_2, "sda_admin")) == 1
