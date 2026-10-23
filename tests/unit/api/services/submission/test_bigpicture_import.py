"""Tests for the Bigpicture import service."""

import re
from types import SimpleNamespace
from typing import Callable, Sequence
from unittest.mock import AsyncMock, MagicMock

import pytest

from metadata_backend.api.exceptions import UserException
from metadata_backend.api.models.models import IngestStatus
from metadata_backend.api.models.sda import DatasetFile, DatasetStatus
from metadata_backend.api.processors.xml.bigpicture import BP_DATASET_OBJECT_TYPE
from metadata_backend.api.services.accession import generate_bp_accession_prefix
from metadata_backend.api.services.project import NbisProjectService
from metadata_backend.api.services.submission.bigpicture_import import BigpictureObjectImportService
from metadata_backend.api.services.submission.submission import ObjectSubmission
from metadata_backend.services.admin_service import AdminServiceHandler
from tests.utils import (
    BP_ANNOTATION_1_FILE,
    BP_IMAGE_1_FILE,
    BP_IMAGE_2_FILE,
    bp_objects,
    bp_objects_with_dataset_id,
)

_SDA_ROOT = "ROOT"


# The metadata version 2.0 XMLs in METADATA/ in the SDA dataset. The import requires the SDA dataset
# to have the same metadata XMLs as it has. Only landing page XML may be added.
_SDA_METADATA_FILES = (
    "dataset.xml.c4gh",
    "policy.xml.c4gh",
    "image.xml.c4gh",
    "annotation.xml.c4gh",
    "observation.xml.c4gh",
    "observer.xml.c4gh",
    "sample.xml.c4gh",
    "staining.xml.c4gh",
)


_DATASET_ID = f"{generate_bp_accession_prefix(BP_DATASET_OBJECT_TYPE)}-abcdef-ghjkmn"


_USER = "user@test"


def _sda_file(accession_id: str, path: str) -> DatasetFile:
    return DatasetFile(id=f"file-{accession_id}", accessionID=accession_id, path=path)


def _sda_data_files() -> list[DatasetFile]:
    return [
        _sda_file("image-1", f"{_SDA_ROOT}/{BP_IMAGE_1_FILE}.c4gh"),
        _sda_file("image-2", f"{_SDA_ROOT}/{BP_IMAGE_2_FILE}.c4gh"),
        _sda_file("annotation-1", f"{_SDA_ROOT}/{BP_ANNOTATION_1_FILE}.c4gh"),
    ]


def _sda_metadata_files(names: Sequence[str] = _SDA_METADATA_FILES) -> list[DatasetFile]:
    return [_sda_file(f"old-{name.removesuffix('.xml.c4gh')}-xml", f"{_SDA_ROOT}/METADATA/{name}") for name in names]


def _sda_files() -> list[DatasetFile]:
    return [*_sda_data_files(), *_sda_metadata_files()]


def _replace_in_xml(objects: list[ObjectSubmission], filename: str, old: str, new: str) -> list[ObjectSubmission]:
    assert any(o.filename == filename and old in o.document for o in objects)
    return [
        ObjectSubmission(filename=o.filename, document=o.document.replace(old, new)) if o.filename == filename else o
        for o in objects
    ]


@pytest.fixture
def admin() -> MagicMock:
    admin = MagicMock(spec=AdminServiceHandler)
    admin.get_dataset_status.return_value = DatasetStatus.RELEASED
    return admin


@pytest.fixture
def import_service(
    submission_service, object_service, file_service, admin
) -> Callable[..., BigpictureObjectImportService]:
    def _create(rems=None) -> BigpictureObjectImportService:
        return BigpictureObjectImportService(
            NbisProjectService(), submission_service, object_service, file_service, admin, rems or _rems()
        )

    return _create


async def test_import(import_service, admin, submission_service, object_service, file_service):
    data_files = _sda_data_files()
    thumbnail = _sda_file("thumbnail-1", f"{_SDA_ROOT}/LANDING_PAGE/THUMBNAILS/thumb.jpg.c4gh")
    # The dataset has no landing page, which the import adds.
    admin.list_ingested_files.return_value = [*data_files, *_sda_metadata_files(), thumbnail]

    submission = await import_service().create(_USER, _USER, bp_objects_with_dataset_id(_DATASET_ID))

    assert submission.submissionId == _DATASET_ID
    assert submission.imported is True
    assert submission.dateImported is not None
    assert await submission_service.is_imported(_DATASET_ID)

    # Other metadata objects are accessioned.
    objects = await object_service.get_objects(_DATASET_ID)
    assert {o.objectId for o in objects if o.objectType == BP_DATASET_OBJECT_TYPE} == {_DATASET_ID}
    assert all(o.objectId for o in objects)
    assert len({o.objectId for o in objects}) == len(objects)

    # The data files and thumbnail are saved in the databae with their SDA paths and accessions,
    # and in the ready state. The old metadata XMLs are not saved. Publishing will later write new ones
    # that replace them in SDA.
    files = {f.path: f async for f in file_service.get_files(submission_id=_DATASET_ID)}
    assert {path: f.fileId for path, f in files.items()} == {
        file.path: file.accession_id for file in [*data_files, thumbnail]
    }
    assert all(f.bytes is None for f in files.values())
    states = await file_service.get_ingest_file_states(_DATASET_ID)
    assert {s.ingest_status for s in states} == {IngestStatus.READY}


async def test_import_with_landing_page(import_service, admin, file_service):
    landing_page = _sda_file("old-landing-page-xml", f"{_SDA_ROOT}/LANDING_PAGE/landing_page.xml.c4gh")
    admin.list_ingested_files.return_value = [*_sda_files(), landing_page]
    submission = await import_service().create(_USER, _USER, bp_objects_with_dataset_id(_DATASET_ID))
    assert submission.submissionId == _DATASET_ID

    # The old landing page XML is not saved as a submission file: publishing writes a new one that replaces it.
    paths = {f.path async for f in file_service.get_files(submission_id=_DATASET_ID)}
    assert landing_page.path not in paths


async def test_import_requires_shared_root(import_service, admin):
    admin.list_ingested_files.return_value = [
        *_sda_files(),
        _sda_file("thumbnail-1", "OTHER/LANDING_PAGE/THUMBNAILS/thumb.jpg.c4gh"),
    ]
    with pytest.raises(UserException, match="files in SDA are not under one root directory"):
        await import_service().create(_USER, _USER, bp_objects_with_dataset_id(_DATASET_ID))


async def test_import_requires_dataset_accession(import_service):
    with pytest.raises(UserException, match="must have an accession"):
        await import_service().create(_USER, _USER, bp_objects(is_update=False)[0])


@pytest.mark.parametrize(
    "dataset_id",
    [
        "BPDST001",
        # Another object type's prefix.
        _DATASET_ID.replace("-dataset-", "-image-"),
        # Characters outside the random part's alphabet.
        f"{_DATASET_ID[:-6]}abcde1",
        f"{_DATASET_ID}/files",
    ],
)
async def test_import_requires_bigpicture_dataset_accession(import_service, admin, dataset_id):
    """The dataset accession must have the format of the dataset accessions SD Submit generates."""
    with pytest.raises(UserException, match=f"accession '{re.escape(dataset_id)}' is not a Bigpicture accession"):
        await import_service().create(_USER, _USER, bp_objects_with_dataset_id(dataset_id))
    admin.list_ingested_files.assert_not_called()


@pytest.mark.parametrize(
    "filename, old, new",
    [
        ("image.xml", '<IMAGE alias="1"', '<IMAGE alias="1" accession="bb-x"'),
        ("dataset.xml", '<IMAGE_REF alias="1"/>', '<IMAGE_REF alias="1" accession="bb-x"/>'),
    ],
)
async def test_import_rejects_other_accessions(import_service, filename, old, new):
    """Only the dataset has an accession, in an object or in a reference."""
    objects = _replace_in_xml(bp_objects_with_dataset_id(_DATASET_ID), filename, old, new)
    with pytest.raises(UserException, match="must not have an accession: 'bb-x'"):
        await import_service().create(_USER, _USER, objects)


async def test_import_rejects_datacite(import_service):
    _, files = bp_objects(is_update=False)
    objects = [
        *bp_objects_with_dataset_id(_DATASET_ID),
        ObjectSubmission(filename="datacite.xml", document=files["datacite.xml"].read_text()),
    ]
    with pytest.raises(UserException, match="DataCite XML is not supported"):
        await import_service().create(_USER, _USER, objects)


async def test_import_dataset_not_in_sda(import_service, admin):
    admin.list_ingested_files.return_value = None
    with pytest.raises(UserException, match="does not exist in SDA"):
        await import_service().create(_USER, _USER, bp_objects_with_dataset_id(_DATASET_ID))


async def test_import_dataset_deprecated(import_service, admin):
    admin.get_dataset_status.return_value = DatasetStatus.DEPRECATED
    with pytest.raises(UserException, match="has been deprecated"):
        await import_service().create(_USER, _USER, bp_objects_with_dataset_id(_DATASET_ID))


async def test_import_already_submitted(import_service, admin):
    admin.list_ingested_files.return_value = _sda_files()
    await import_service().create(_USER, _USER, bp_objects_with_dataset_id(_DATASET_ID))

    with pytest.raises(UserException, match="has already been submitted"):
        # Dataset can't be imported the second time.
        await import_service().create(_USER, _USER, bp_objects_with_dataset_id(_DATASET_ID))


async def test_import_file_mismatch(import_service, admin):
    # A file is matched by its path, so one in another directory is not matched.
    admin.list_ingested_files.return_value = [
        _sda_file("image-1", f"{_SDA_ROOT}/test.dcm.c4gh"),
        *_sda_data_files()[1:],
        *_sda_metadata_files(),
    ]
    with pytest.raises(UserException) as e:
        await import_service().create(_USER, _USER, bp_objects_with_dataset_id(_DATASET_ID))
    assert f"has no file '{BP_IMAGE_1_FILE}' in SDA" in str(e.value)
    assert "has file 'test.dcm' in SDA, which is not imported" in str(e.value)


async def test_import_metadata_file_mismatch(import_service, admin):
    names = [name for name in _SDA_METADATA_FILES if name != "policy.xml.c4gh"] + ["ontology.xml.c4gh"]
    admin.list_ingested_files.return_value = [*_sda_data_files(), *_sda_metadata_files(names)]
    with pytest.raises(UserException) as e:
        await import_service().create(_USER, _USER, bp_objects_with_dataset_id(_DATASET_ID))
    assert "has no metadata file 'METADATA/policy.xml' in SDA" in str(e.value)
    assert "has metadata file 'METADATA/ontology.xml' in SDA, which is not imported" in str(e.value)


def _rems(resources=(), catalogue_items=(), organization_id: str = "nbn") -> SimpleNamespace:
    """A REMS double whose workflow 1 belongs to the organization of the test rems.xml."""
    return SimpleNamespace(
        get_workflow=AsyncMock(return_value=SimpleNamespace(organization=SimpleNamespace(id=organization_id))),
        get_resources=AsyncMock(return_value=list(resources)),
        get_catalogue_items=AsyncMock(return_value=list(catalogue_items)),
    )


def _rems_resource(resid: str = _DATASET_ID, organization_id: str = "nbn") -> SimpleNamespace:
    return SimpleNamespace(id=1, resid=resid, organization=SimpleNamespace(id=organization_id))


def _rems_catalogue_item(
    resid: str = _DATASET_ID, workflow_id: int = 1, organization_id: str = "nbn", resource_id: int = 1
) -> SimpleNamespace:
    return SimpleNamespace(
        id=2,
        resid=resid,
        resource_id=resource_id,
        workflow_id=workflow_id,
        organization=SimpleNamespace(id=organization_id),
        expired=False,
    )


async def _import_with_rems(import_service, admin, rems) -> None:
    admin.list_ingested_files.return_value = _sda_files()
    await import_service(rems).create(_USER, _USER, bp_objects_with_dataset_id(_DATASET_ID))


async def test_import_without_rems_resource(import_service, admin):
    rems = _rems()
    await _import_with_rems(import_service, admin, rems)
    rems.get_resources.assert_awaited_once_with(_DATASET_ID)
    rems.get_catalogue_items.assert_awaited_once_with(_DATASET_ID)


async def test_import_with_rems_resource(import_service, admin):
    # The import succeeds only if the catalogue item is checked against the existing resource, which
    # publishing will reuse.
    rems = _rems([_rems_resource()], [_rems_catalogue_item()])
    await _import_with_rems(import_service, admin, rems)
    rems.get_resources.assert_awaited_once_with(_DATASET_ID)
    rems.get_catalogue_items.assert_awaited_once_with(_DATASET_ID)


async def test_import_rems_resource_of_other_organization(import_service, admin):
    rems = _rems([_rems_resource(organization_id="other")])
    with pytest.raises(UserException, match="belongs to REMS organization 'other', not 'nbn'"):
        await _import_with_rems(import_service, admin, rems)


async def test_import_rems_catalogue_item_of_other_workflow(import_service, admin):
    rems = _rems([_rems_resource()], [_rems_catalogue_item(workflow_id=7)])
    with pytest.raises(UserException, match="has REMS workflow '7', not '1'"):
        await _import_with_rems(import_service, admin, rems)


async def test_import_several_rems_catalogue_items(import_service, admin):
    rems = _rems([_rems_resource()], [_rems_catalogue_item(), _rems_catalogue_item()])
    with pytest.raises(UserException, match="has several catalogue items"):
        await _import_with_rems(import_service, admin, rems)


async def test_import_rems_catalogue_item_of_other_resource(import_service, admin):
    rems = _rems([_rems_resource()], [_rems_catalogue_item(resource_id=55)])
    with pytest.raises(UserException, match="belongs to REMS resource '55', not to the active REMS resource '1'"):
        await _import_with_rems(import_service, admin, rems)


async def test_import_rems_catalogue_item_without_active_resource(import_service, admin):
    # The resource of the catalogue item is archived, so publishing would create a new resource.
    rems = _rems([], [_rems_catalogue_item(resource_id=55)])
    with pytest.raises(UserException, match="belongs to REMS resource '55', not to an active REMS resource"):
        await _import_with_rems(import_service, admin, rems)
