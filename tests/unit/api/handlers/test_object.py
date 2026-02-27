"""Test API endpoints from ObjectAPIHandler."""

import copy
import io
import json
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, BinaryIO

from metadata_backend.api.models.models import Files, Object, Objects
from metadata_backend.api.models.submission import Submission, SubmissionWorkflow
from metadata_backend.api.processors.xml.bigpicture import (
    BP_ANNOTATION_OBJECT_TYPE,
    BP_ANNOTATION_SCHEMA,
    BP_DATASET_OBJECT_TYPE,
    BP_DATASET_SCHEMA,
    BP_FULL_SUBMISSION_XML_OBJECT_CONFIG,
    BP_IMAGE_OBJECT_TYPE,
    BP_IMAGE_SCHEMA,
    BP_LANDING_PAGE_OBJECT_TYPE,
    BP_LANDING_PAGE_SCHEMA,
    BP_OBSERVATION_OBJECT_TYPE,
    BP_OBSERVATION_SCHEMA,
    BP_OBSERVER_OBJECT_TYPE,
    BP_OBSERVER_SCHEMA,
    BP_ORGANISATION_OBJECT_TYPE,
    BP_ORGANISATION_SCHEMA,
    BP_POLICY_OBJECT_TYPE,
    BP_POLICY_SCHEMA,
    BP_REMS_OBJECT_TYPE,
    BP_REMS_SCHEMA,
    BP_SAMPLE_BIOLOGICAL_BEING_OBJECT_TYPE,
    BP_SAMPLE_BLOCK_OBJECT_TYPE,
    BP_SAMPLE_CASE_OBJECT_TYPE,
    BP_SAMPLE_SCHEMA,
    BP_SAMPLE_SLIDE_OBJECT_TYPE,
    BP_SAMPLE_SPECIMEN_OBJECT_TYPE,
    BP_STAINING_OBJECT_TYPE,
    BP_STAINING_SCHEMA,
)
from metadata_backend.api.processors.xml.processors import XmlDocumentProcessor, XmlProcessor
from metadata_backend.api.services.accession import generate_bp_accession_prefix
from metadata_backend.conf.conf import API_PREFIX
from tests.unit.patches.user import (
    MOCK_PROJECT_ID,
    patch_get_user_projects,
    patch_verify_authorization,
    patch_verify_user_project,
)
from tests.utils import bp_submission_documents, bp_update_documents, sd_submission_dict

from ..processors.xml.test_datacite import assert_datacite

TEST_ROOT_DIR = Path(__file__).parent.parent.parent.parent / "test_files"
BP_SUBMISSION_DIR = TEST_ROOT_DIR / "xml" / "bigpicture"
DATACITE_SUBMISSION_DIR = TEST_ROOT_DIR / "xml" / "datacite"


def prepare_file_data_sd(_bytes: BinaryIO | dict[str, Any]) -> list[tuple[str, tuple[str, BinaryIO, str]]]:
    """Prepare multipart file data for SD submission."""
    if isinstance(_bytes, dict):
        _bytes = io.BytesIO(json.dumps(_bytes).encode("utf-8"))  # type: ignore
    return [("file", ("submission.json", _bytes, "application/json"))]


def prepare_file_data_bp(_files) -> list[tuple[str, tuple[str, BinaryIO, str]]]:
    """Prepare multipart file data for BP submission."""
    files = []
    for name, _bytes in _files.items():
        files.append((name, (name, _bytes, "application/xml")))
    return files


async def test_submission_sd(csc_client):
    """Test SD submission."""

    project_id = MOCK_PROJECT_ID

    submission_dict = sd_submission_dict()
    submission_name = submission_dict["name"]

    file_data = prepare_file_data_sd(submission_dict)

    with patch_verify_user_project, patch_verify_authorization:
        # Check that submission does not exists.
        response = csc_client.head(f"{API_PREFIX}/submit/{submission_name}?projectId={project_id}")
        assert response.status_code == 404

        # Test create submission.
        #

        response = csc_client.post(f"{API_PREFIX}/submit?projectId={project_id}", files=file_data)
        assert response.status_code == 200
        submission = Submission.model_validate(response.json())

        # Assert submission document.
        submission_id = submission.submissionId
        assert submission.name == submission_name
        assert submission.title == "TestTitle"
        assert submission.description == "TestDescription"
        assert submission_id is not None

        # Assert rems.
        assert submission.rems.workflowId == 1
        assert submission.rems.organizationId is None  # Optional

        # Assert datacite.
        assert_datacite(submission.metadata, saved=True)

        # Test get submission document.
        response = csc_client.get(f"{API_PREFIX}/submissions/{submission_id}")
        assert response.status_code == 200
        assert submission == Submission.model_validate(response.json())

        async def _assert_update(_data: dict[str, Any]):
            assert submission.model_dump(exclude={"lastModified", "bucket"}) == Submission.model_validate(
                _data
            ).model_dump(exclude={"lastModified", "bucket"})

        async def _assert_not_allowed(_response):
            assert _response.status_code == 400
            assert "can't be changed to" in _response.text

        # Test update of full document with changed submission title and description.
        submission.title = "UpdatedTestTitle"
        submission.description = "UpdatedTestDescription"
        submission_dict["title"] = submission.title
        submission_dict["description"] = submission.description

        file_data = prepare_file_data_sd(submission_dict)

        response = csc_client.patch(f"{API_PREFIX}/submit/{submission_id}?projectId={project_id}", files=file_data)
        assert response.status_code == 200

        response = csc_client.get(f"{API_PREFIX}/submissions/{submission_id}")
        assert response.status_code == 200
        await _assert_update(response.json())

        # Test update of submission title and description only.
        submission.title = "UpdatedTestTitle2"
        submission.description = "UpdatedTestDescription2"

        file_data = prepare_file_data_sd({"title": submission.title, "description": submission.description})

        response = csc_client.patch(f"{API_PREFIX}/submit/{submission_id}?projectId={project_id}", files=file_data)
        assert response.status_code == 200

        response = csc_client.get(f"{API_PREFIX}/submissions/{submission_id}")
        assert response.status_code == 200
        await _assert_update(response.json())

        # Test set submission bucket.

        file_data = prepare_file_data_sd({"bucket": f"bucket_{uuid.uuid4()}"})
        response = csc_client.patch(f"{API_PREFIX}/submit/{submission_id}?projectId={project_id}", files=file_data)
        assert response.status_code == 200

        response = csc_client.get(f"{API_PREFIX}/submissions/{submission_id}")
        assert response.status_code == 200
        await _assert_update(response.json())

        # Test update of submission bucket (not allowed).

        file_data = prepare_file_data_sd({"bucket": f"bucket_{uuid.uuid4()}"})
        response = csc_client.patch(f"{API_PREFIX}/submit/{submission_id}?projectId={project_id}", files=file_data)
        await _assert_not_allowed(response)

        # Test update of workflow (not allowed).

        file_data = prepare_file_data_sd(
            {
                "workflow": SubmissionWorkflow.BP.value,
            }
        )
        response = csc_client.patch(f"{API_PREFIX}/submit/{submission_id}?projectId={project_id}", files=file_data)
        await _assert_not_allowed(response)

        # Test update of project id (not allowed).
        file_data = prepare_file_data_sd({"projectId": f"project_{uuid.uuid4()}"})
        response = csc_client.patch(f"{API_PREFIX}/submit/{submission_id}?projectId={project_id}", files=file_data)
        await _assert_not_allowed(response)


async def test_submission_bp(nbis_client):
    """Test BigPicture submission."""

    project_id = MOCK_PROJECT_ID
    xml_config = BP_FULL_SUBMISSION_XML_OBJECT_CONFIG

    for is_datacite in [True, False]:
        # Read XML files.
        submission_name, object_names, files = bp_submission_documents(is_datacite=is_datacite)
        file_data = prepare_file_data_bp(files)

        sample_object_types = {
            BP_SAMPLE_BIOLOGICAL_BEING_OBJECT_TYPE: ["1"],
            BP_SAMPLE_SLIDE_OBJECT_TYPE: ["1"],
            BP_SAMPLE_SPECIMEN_OBJECT_TYPE: ["1"],
            BP_SAMPLE_BLOCK_OBJECT_TYPE: ["1"],
            BP_SAMPLE_CASE_OBJECT_TYPE: ["1"],
        }
        for object_type, original_names in sample_object_types.items():
            sample_object_types[object_type] = [object_names[BP_SAMPLE_SCHEMA][object_type][original_names[0]]]

        object_types = {
            BP_ANNOTATION_OBJECT_TYPE: [object_names[BP_ANNOTATION_SCHEMA][BP_ANNOTATION_OBJECT_TYPE]["1"]],
            BP_DATASET_OBJECT_TYPE: [object_names[BP_DATASET_SCHEMA][BP_DATASET_OBJECT_TYPE]["1"]],
            BP_IMAGE_OBJECT_TYPE: [
                object_names[BP_IMAGE_SCHEMA][BP_IMAGE_OBJECT_TYPE]["1"],
                object_names[BP_IMAGE_SCHEMA][BP_IMAGE_OBJECT_TYPE]["2"],
            ],
            BP_LANDING_PAGE_OBJECT_TYPE: [object_names[BP_LANDING_PAGE_SCHEMA][BP_LANDING_PAGE_OBJECT_TYPE]["1"]],
            BP_OBSERVATION_OBJECT_TYPE: [object_names[BP_OBSERVATION_SCHEMA][BP_OBSERVATION_OBJECT_TYPE]["1"]],
            BP_OBSERVER_OBJECT_TYPE: [object_names[BP_OBSERVER_SCHEMA][BP_OBSERVER_OBJECT_TYPE]["1"]],
            BP_ORGANISATION_OBJECT_TYPE: [object_names[BP_ORGANISATION_SCHEMA][BP_ORGANISATION_OBJECT_TYPE]["1"]],
            BP_POLICY_OBJECT_TYPE: [object_names[BP_POLICY_SCHEMA][BP_POLICY_OBJECT_TYPE]["1"]],
            BP_REMS_OBJECT_TYPE: [object_names[BP_REMS_SCHEMA][BP_REMS_OBJECT_TYPE]["1"]],
            BP_STAINING_OBJECT_TYPE: [object_names[BP_STAINING_SCHEMA][BP_STAINING_OBJECT_TYPE]["1"]],
            **sample_object_types,
        }

        with patch_get_user_projects, patch_verify_user_project, patch_verify_authorization:
            # Check that submission does not exists.
            response = nbis_client.head(f"{API_PREFIX}/submit/{submission_name}")
            assert response.status_code == 404

            # Test create submission.
            response = nbis_client.post(f"{API_PREFIX}/submit", files=file_data)
            assert response.status_code == 200
            submission = Submission.model_validate(response.json())
            submission_id = submission.submissionId

            # Assert submission document.
            await _assert_bp_submission(submission, submission_id, submission_name)

            # Assert rems.
            await assert_bp_rems(submission)

            # Assert datacite.
            if is_datacite:
                assert_datacite(submission.metadata, saved=True)

            # Assert metadata objects.
            await assert_bp_metadata_objects(nbis_client, submission, object_types, sample_object_types, xml_config)

            # Assert files.
            await assert_bp_files(nbis_client, submission_id)

            created_objects = await list_metadata_objects(nbis_client, project_id, True, submission_name)

            # Test update submission (dataset and image changes).
            #

            # Read XML files.
            _, object_names, files = bp_update_documents(submission_name, object_names, is_datacite)
            file_data = prepare_file_data_bp(files)

            updated_object_types = copy.deepcopy(object_types)
            updated_object_types[BP_IMAGE_OBJECT_TYPE] = [
                object_names[BP_IMAGE_SCHEMA][BP_IMAGE_OBJECT_TYPE]["1"],
                object_names[BP_IMAGE_SCHEMA][BP_IMAGE_OBJECT_TYPE]["3"],
            ]

            response = nbis_client.patch(f"{API_PREFIX}/submit/{submission_id}", files=file_data)
            assert response.status_code == 200

            response = nbis_client.get(f"{API_PREFIX}/submissions/{submission_id}")
            assert response.status_code == 200
            submission = Submission.model_validate(response.json())

            # Assert submission document.
            await _assert_bp_submission(submission, submission_id, submission_name, is_update=True)

            # Assert rems.
            await assert_bp_rems(submission)

            # Assert datacite.
            if is_datacite:
                assert_datacite(submission.metadata, saved=True)

            # Assert metadata objects.
            await assert_bp_metadata_objects(
                nbis_client, submission, updated_object_types, sample_object_types, xml_config
            )

            # Assert files.
            await assert_bp_files(nbis_client, submission_id, is_update=True)

            def _assert_unchanged_object(_created_obj, _updated_obj):
                assert _created_obj.objectId == _updated_obj.objectId
                assert _created_obj.objectType == _updated_obj.objectType
                assert _created_obj.submissionId == _updated_obj.submissionId
                assert _created_obj.title == _updated_obj.title
                assert _created_obj.description == _updated_obj.description
                assert _created_obj.created == _updated_obj.created
                assert _created_obj.modified < _updated_obj.modified

            # Assert submission document.
            await _assert_bp_submission(submission, submission_id, submission_name, is_update=True)

            # Assert rems.
            await assert_bp_rems(submission)

            # Assert datacite.
            if is_datacite:
                assert_datacite(submission.metadata, saved=True)

            # Assert metadata objects.
            await assert_bp_metadata_objects(
                nbis_client, submission, updated_object_types, sample_object_types, xml_config
            )

            # Assert files.
            await assert_bp_files(nbis_client, submission_id, is_update=True)

            updated_objects = await list_metadata_objects(nbis_client, project_id, True, submission_name)

            created_object_lookup = {(o.objectType, o.name): o for o in created_objects}
            updated_object_lookup = {(o.objectType, o.name): o for o in updated_objects}

            # Assert that non-image and non-dataset metadata object rows have not been changed.
            for created_obj in created_objects:
                if created_obj.objectType not in [BP_DATASET_OBJECT_TYPE, BP_IMAGE_OBJECT_TYPE]:
                    updated_obj = updated_object_lookup.get((created_obj.objectType, created_obj.name))
                    assert updated_obj is not None, (
                        f"Updated '{created_obj.objectType}' metadata object '{created_obj.name}' not found"
                    )
                    _assert_unchanged_object(created_obj, updated_obj)

            # Assert image metadata objects.
            for created_obj in created_objects:
                if created_obj.objectType == BP_IMAGE_OBJECT_TYPE:
                    updated_obj = updated_object_lookup.get((created_obj.objectType, created_obj.name))
                    if created_obj.name in updated_object_types[BP_IMAGE_OBJECT_TYPE]:
                        # Check that the object still exists.
                        assert updated_obj is not None, (
                            f"Updated '{created_obj.objectType}' metadata object '{created_obj.name}' not found"
                        )
                        _assert_unchanged_object(created_obj, updated_obj)
                    else:
                        # Check that the object has been removed.
                        assert updated_obj is None
            for updated_obj in updated_objects:
                if updated_obj.objectType == BP_IMAGE_OBJECT_TYPE:
                    created_obj = created_object_lookup.get((updated_obj.objectType, updated_obj.name))
                    if updated_obj.name in object_types[BP_IMAGE_OBJECT_TYPE]:
                        # Check that the object was created previously.
                        assert created_obj is not None, (
                            f"Created '{updated_obj.objectType}' metadata object '{updated_obj.name}' not found"
                        )
                        _assert_unchanged_object(created_obj, updated_obj)
                    else:
                        # Check that the object has been assigned a new id.
                        assert updated_obj.objectId not in [o.objectId for o in created_objects]


async def _assert_bp_submission(submission, submission_id, submission_name, is_update: bool = False):
    assert submission.name == submission_name
    if is_update:
        assert submission.title == "updated_test_title"
        assert submission.description == "updated_test_description"
    else:
        assert submission.title == "test_title"
        assert submission.description == "test_description"
    assert submission_id.startswith(generate_bp_accession_prefix(BP_DATASET_OBJECT_TYPE))


async def assert_bp_rems(submission):
    assert submission.rems.workflowId == 1
    assert submission.rems.organizationId == "nbn"


async def assert_bp_metadata_objects(nbis_client, expected_submission, object_types, sample_object_types, xml_config):
    project_id = expected_submission.projectId
    submission_id = expected_submission.submissionId
    submission_name = expected_submission.name

    async def _assert_xml_objects(
        response_, object_names_: dict[str, list[str]], object_ids_: dict[str, dict[str, str]]
    ) -> None:
        """Assert that all XML documents are returned."""
        assert response_.status_code == 200

        xml_ = response_.content
        doc_processor_ = XmlDocumentProcessor(xml_config, XmlProcessor.parse_xml(xml_))
        try:
            # Assert processor object types.
            assert sorted(object_type_ for object_type_, names_ in object_names_.items() for _ in names_) == sorted(
                p.object_type for p in doc_processor_.xml_processors
            )
            # Assert processor object names.
            assert sorted(
                name_ for object_type_ in object_names_.keys() for name_ in object_names_[object_type_]
            ) == sorted(p.get_xml_object_identifier().name for p in doc_processor_.xml_processors)
            # Assert processor object ids.
            x = []
            for object_type_, names_ in object_names_.items():
                for name_ in names_:
                    try:
                        x.append(object_ids_[object_type_][name_])
                    except Exception as e:
                        raise e

            assert sorted(object_ids_[t][n] for t, names in object_names_.items() for n in names) == sorted(
                p.get_xml_object_identifier().id for p in doc_processor_.xml_processors
            )
        except Exception as e:
            raise e

    # Test get submission document.
    response = nbis_client.get(f"{API_PREFIX}/submissions/{submission_id}")
    assert response.status_code == 200
    assert expected_submission == Submission.model_validate(response.json())

    # Retrieve both by submission id and submission name.
    for submission_id_or_name in (submission_id, submission_name):
        is_submission_name = submission_id_or_name == submission_name

        # Test list metadata objects.
        objects = await list_metadata_objects(nbis_client, project_id, is_submission_name, submission_id_or_name)
        object_ids = defaultdict(dict)
        for o in objects:
            object_ids[o.objectType][o.name] = o.objectId

        # Assert object names.
        for object_type, object_names in object_types.items():
            assert set(object_names) == set(o.name for o in objects if o.objectType == object_type)

        if is_submission_name:
            docs_url = f"{API_PREFIX}/submissions/{submission_id_or_name}/objects/docs?projectId={project_id}&"
        else:
            docs_url = f"{API_PREFIX}/submissions/{submission_id_or_name}/objects/docs?"

        for object_type, object_names in object_types.items():
            schema_type = xml_config.get_schema_type(object_type)

            # Test get metadata documents by object type.
            response = nbis_client.get(f"{docs_url}objectType={object_type}")
            # Multiple documents may be returned.
            await _assert_xml_objects(response, {k: v for k, v in object_types.items() if object_type == k}, object_ids)

            # Test get metadata documents by schema type.
            response = nbis_client.get(f"{docs_url}schemaType={schema_type}")
            if object_type in sample_object_types:
                # Multiple sample documents of different object types may be returned.
                await _assert_xml_objects(response, {k: v for k, v in sample_object_types.items()}, object_ids)
            else:
                # Multiple documents may be returned.
                await _assert_xml_objects(
                    response, {k: v for k, v in object_types.items() if object_type == k}, object_ids
                )

            for object_name in object_names:
                object_id = object_ids[object_type][object_name]

                # Test get metadata documents by object type and object name.
                response = nbis_client.get(f"{docs_url}objectType={object_type}&objectName={object_name}")
                await _assert_xml_objects(response, {object_type: [object_name]}, object_ids)

                # Test get metadata documents by object type and object id.
                response = nbis_client.get(f"{docs_url}objectType={object_type}&objectId={object_id}")
                await _assert_xml_objects(response, {object_type: [object_name]}, object_ids)

                # Test get metadata documents by schema type and object name.
                response = nbis_client.get(f"{docs_url}schemaType={schema_type}&objectName={object_name}")
                if object_type in sample_object_types:
                    # Multiple sample documents of different object types may be returned.
                    await _assert_xml_objects(
                        response,
                        {k: [object_name] for k, v in sample_object_types.items() if object_name in v},
                        object_ids,
                    )
                else:
                    await _assert_xml_objects(response, {object_type: [object_name]}, object_ids)

                # Test get metadata documents by schema type and object id. Returns a single document.
                response = nbis_client.get(f"{docs_url}schemaType={schema_type}&objectId={object_id}")
                await _assert_xml_objects(response, {object_type: [object_name]}, object_ids)


async def assert_bp_files(nbis_client, submission_id, is_update=False):
    files_url = f"{API_PREFIX}/submissions/{submission_id}/files"
    response = nbis_client.get(files_url)
    assert response.status_code == 200
    files = Files.model_validate(response.json()).root

    def _assert_file(
        _files, path: str, checksum_method: str, encrypted_checksum: str, unencrypted_checksum: str | None
    ):
        for file in _files:
            if file.path == path:
                assert file.checksumMethod == checksum_method
                assert file.encryptedChecksum == encrypted_checksum
                assert file.unencryptedChecksum == unencrypted_checksum
                return

        raise AssertionError(f"File with path {path!r} not found")

    # Assert image files.
    if not is_update:
        _assert_file(
            files,
            "test.dcm",
            "SHA256",
            "8c3a51adf8f8b1b7a2625d7ac9c12a08dcf9e6a10e87a1f8a215e67f87e7d2a4",
            "8c3a51adf8f8b1b7a2625d7ac9c12a08dcf9e6a10e87a1f8a215e67f87e7d2a4",
        )
        _assert_file(
            files,
            "test2.dcm",
            "SHA256",
            "2c3a51adf8f8b1b7a2625d7ac9c12a08dcf9e6a10e87a1f8a215e67f87e7d2a4",
            "2c3a51adf8f8b1b7a2625d7ac9c12a08dcf9e6a10e87a1f8a215e67f87e7d2a4",
        )
    else:
        _assert_file(
            files,
            "test.dcm",
            "SHA256",
            "8c3a51adf8f8b1b7a2625d7ac9c12a08dcf9e6a10e87a1f8a215e67f87e7d2a4",
            "8c3a51adf8f8b1b7a2625d7ac9c12a08dcf9e6a10e87a1f8a215e67f87e7d2a4",
        )
        _assert_file(
            files,
            "test3.dcm",
            "SHA256",
            "3c3a51adf8f8b1b7a2625d7ac9c12a08dcf9e6a10e87a1f8a215e67f87e7d2a4",
            "3c3a51adf8f8b1b7a2625d7ac9c12a08dcf9e6a10e87a1f8a215e67f87e7d2a4",
        )

        # Assert annotation files.
        _assert_file(
            files, "test.json", "SHA256", "8c3a51adf8f8b1b7a2625d7ac9c12a08dcf9e6a10e87a1f8a215e67f87e7d2a4", None
        )


async def list_metadata_objects(client, project_id, is_submission_name, submission_id_or_name) -> list[Object]:
    if is_submission_name:
        objects_url = f"{API_PREFIX}/submissions/{submission_id_or_name}/objects?projectId={project_id}"
    else:
        objects_url = f"{API_PREFIX}/submissions/{submission_id_or_name}/objects"
    response = client.get(objects_url)
    assert response.status_code == 200
    objects = Objects.model_validate(response.json()).root
    return objects
