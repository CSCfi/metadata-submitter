"""Test API endpoints from ObjectAPIHandler."""

import io
import json
import uuid
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree

from metadata_backend.api.models.models import Files, Objects
from metadata_backend.api.models.submission import Submission, SubmissionWorkflow
from metadata_backend.api.processors.xml.bigpicture import (
    BP_ANNOTATION_OBJECT_TYPE,
    BP_DATASET_OBJECT_TYPE,
    BP_FULL_SUBMISSION_XML_OBJECT_CONFIG,
    BP_IMAGE_OBJECT_TYPE,
    BP_LANDING_PAGE_OBJECT_TYPE,
    BP_OBSERVATION_OBJECT_TYPE,
    BP_OBSERVER_OBJECT_TYPE,
    BP_ORGANISATION_OBJECT_TYPE,
    BP_POLICY_OBJECT_TYPE,
    BP_REMS_OBJECT_TYPE,
    BP_SAMPLE_BIOLOGICAL_BEING_OBJECT_TYPE,
    BP_SAMPLE_BLOCK_OBJECT_TYPE,
    BP_SAMPLE_CASE_OBJECT_TYPE,
    BP_SAMPLE_SLIDE_OBJECT_TYPE,
    BP_SAMPLE_SPECIMEN_OBJECT_TYPE,
    BP_STAINING_OBJECT_TYPE,
)
from metadata_backend.api.processors.xml.processors import XmlDocumentProcessor, XmlProcessor
from metadata_backend.api.services.accession import generate_bp_accession_prefix
from metadata_backend.conf.conf import API_PREFIX

from ..processors.xml.test_datacite import assert_datacite
from .common import HandlersTestCase

TEST_ROOT_DIR = Path(__file__).parent.parent.parent.parent / "test_files"
SUBMISSION_JSON = TEST_ROOT_DIR / "submission" / "submission.json"
BP_SUBMISSION_DIR = TEST_ROOT_DIR / "xml" / "bigpicture"
DATACITE_SUBMISSION_DIR = TEST_ROOT_DIR / "xml" / "datacite"


class ObjectHandlerTestCase(HandlersTestCase):
    """Object API endpoint class test cases."""

    async def test_submission_sd(self):
        """Test SD submission."""

        workflow = SubmissionWorkflow.SD.value
        project_id = self.project_id

        file_data = SUBMISSION_JSON.open("rb")

        # Get submission name.
        submission_name = json.load(file_data).get("name")
        file_data.seek(0)

        with self.patch_verify_user_project, self.patch_verify_authorization:
            # Check if submission exists.
            response = await self.client.head(
                f"{API_PREFIX}/submit/{workflow}/{submission_name}?projectId={project_id}"
            )
            assert response.status in (204, 404)

            # Delete submission if it exists.
            response = await self.client.delete(
                f"{API_PREFIX}/submit/{workflow}/{submission_name}?projectId={project_id}"
            )
            assert response.status == 204

            # Check if submission exists.
            response = await self.client.head(
                f"{API_PREFIX}/submit/{workflow}/{submission_name}?projectId={project_id}"
            )
            assert response.status == 404

            # Test create submission.
            #
            response = await self.client.post(f"{API_PREFIX}/submit/{workflow}?projectId={project_id}", data=file_data)
            assert response.status == 200
            submission = Submission.model_validate(await response.json())

            # Assert submission document.
            submission_id = submission.submissionId
            assert submission.name == submission_name
            assert submission.title == "TestTitle"
            assert submission.description == "TestDescription"
            assert submission_id is not None

            # Assert rems.
            assert submission.rems.workflowId == 1
            assert submission.rems.organizationId == "CSC"

            # Assert datacite.
            assert_datacite(submission.metadata, saved=True)

            # Test get submission document.
            response = await self.client.get(f"{API_PREFIX}/submissions/{submission_id}")
            assert response.status == 200
            assert submission == Submission.model_validate(await response.json())

            async def _assert_update(_response):
                assert _response.status == 200
                assert submission.model_dump(exclude={"lastModified", "bucket"}) == Submission.model_validate(
                    await _response.json()
                ).model_dump(exclude={"lastModified", "bucket"})

            async def _assert_not_allowed(_response):
                assert _response.status == 400
                assert "can't be changed to" in await _response.text()

            # Test update of full document with changed submission title and description.
            submission.title = "UpdatedTestTitle"
            submission.description = "UpdatedTestDescription"
            file_data = SUBMISSION_JSON.open("rb")
            updated_submission_dict = json.load(file_data)
            updated_submission_dict["title"] = submission.title
            updated_submission_dict["description"] = submission.description
            submission_bytes = json.dumps(updated_submission_dict).encode("utf-8")
            file_data = io.BytesIO(submission_bytes)  # type: ignore

            response = await self.client.patch(
                f"{API_PREFIX}/submit/{workflow}/{submission_id}?projectId={project_id}", data=file_data
            )
            await _assert_update(response)

            # Test update of submission title and description only.
            submission.title = "UpdatedTestTitle2"
            submission.description = "UpdatedTestDescription2"
            response = await self.client.patch(
                f"{API_PREFIX}/submit/{workflow}/{submission_id}?projectId={project_id}",
                json={"title": submission.title, "description": submission.description},
            )
            await _assert_update(response)

            # Test set submission bucket.
            response = await self.client.patch(
                f"{API_PREFIX}/submit/{workflow}/{submission_id}?projectId={project_id}",
                json={"bucket": f"bucket_{uuid.uuid4()}"},
            )
            await _assert_update(response)

            # Test update of submission bucket (not allowed).
            response = await self.client.patch(
                f"{API_PREFIX}/submit/{workflow}/{submission_id}?projectId={project_id}",
                json={"bucket": f"bucket_{uuid.uuid4()}"},
            )
            await _assert_not_allowed(response)

            # Test update of workflow (not allowed).
            response = await self.client.patch(
                f"{API_PREFIX}/submit/{workflow}/{submission_id}?projectId={project_id}",
                json={"workflow": SubmissionWorkflow.BP.value},
            )
            await _assert_not_allowed(response)

            # Test update of project id (not allowed).
            response = await self.client.patch(
                f"{API_PREFIX}/submit/{workflow}/{submission_id}?projectId={project_id}",
                json={"projectId": f"project_{uuid.uuid4()}"},
            )
            await _assert_not_allowed(response)

    async def test_submission_bp(self):
        """Test BigPicture submission."""

        workflow = SubmissionWorkflow.BP.value
        project_id = self.project_id
        xml_config = BP_FULL_SUBMISSION_XML_OBJECT_CONFIG

        bp_files = [
            "dataset.xml",
            "policy.xml",
            "image.xml",
            "annotation.xml",
            "observation.xml",
            "observer.xml",
            "sample.xml",
            "staining.xml",
            "landing_page.xml",
            "rems.xml",
            "organisation.xml",
        ]
        updated_bp_files = [
            "dataset.xml",
            "policy.xml",
            "update/image.xml",
            "annotation.xml",
            "observation.xml",
            "observer.xml",
            "sample.xml",
            "staining.xml",
            "landing_page.xml",
            "rems.xml",
            "organisation.xml",
        ]
        datacite_files = [
            "datacite.xml",
        ]

        sample_object_types = {
            BP_SAMPLE_BIOLOGICAL_BEING_OBJECT_TYPE: ["1"],
            BP_SAMPLE_SLIDE_OBJECT_TYPE: ["1"],
            BP_SAMPLE_SPECIMEN_OBJECT_TYPE: ["1"],
            BP_SAMPLE_BLOCK_OBJECT_TYPE: ["1"],
            BP_SAMPLE_CASE_OBJECT_TYPE: ["1"],
        }
        object_types = {
            BP_ANNOTATION_OBJECT_TYPE: ["1"],
            BP_DATASET_OBJECT_TYPE: ["1"],
            BP_IMAGE_OBJECT_TYPE: ["1", "2"],
            BP_LANDING_PAGE_OBJECT_TYPE: ["1"],
            BP_OBSERVATION_OBJECT_TYPE: ["1"],
            BP_OBSERVER_OBJECT_TYPE: ["1"],
            BP_ORGANISATION_OBJECT_TYPE: ["1"],
            BP_POLICY_OBJECT_TYPE: ["1"],
            BP_REMS_OBJECT_TYPE: ["1"],
            BP_STAINING_OBJECT_TYPE: ["1"],
            **sample_object_types,
        }
        updated_object_types = {
            BP_ANNOTATION_OBJECT_TYPE: ["1"],
            BP_DATASET_OBJECT_TYPE: ["1"],
            BP_IMAGE_OBJECT_TYPE: ["1", "3"],
            BP_LANDING_PAGE_OBJECT_TYPE: ["1"],
            BP_OBSERVATION_OBJECT_TYPE: ["1"],
            BP_OBSERVER_OBJECT_TYPE: ["1"],
            BP_ORGANISATION_OBJECT_TYPE: ["1"],
            BP_POLICY_OBJECT_TYPE: ["1"],
            BP_REMS_OBJECT_TYPE: ["1"],
            BP_STAINING_OBJECT_TYPE: ["1"],
            **sample_object_types,
        }

        for test_datacite in [True, False]:
            # Read XML files.
            file_data = await self._read_submission_files(bp_files, datacite_files, test_datacite)

            # Get submission name.
            dataset_xml = ElementTree.parse(file_data["dataset.xml"]).getroot()
            submission_name = [elem.text for elem in dataset_xml.findall(".//SHORT_NAME")][0]
            file_data["dataset.xml"].seek(0)

            with self.patch_get_user_projects, self.patch_verify_user_project, self.patch_verify_authorization:
                # Check if submission exists.
                response = await self.client.head(f"{API_PREFIX}/submit/{workflow}/{submission_name}")
                assert response.status in (204, 404)

                # Delete submission if it exists.
                response = await self.client.delete(f"{API_PREFIX}/submit/{workflow}/{submission_name}")
                assert response.status == 204

                # Check if submission exists.
                response = await self.client.head(f"{API_PREFIX}/submit/{workflow}/{submission_name}")
                assert response.status == 404

                # Test create submission.
                #

                response = await self.client.post(f"{API_PREFIX}/submit/{workflow}", data=file_data)
                assert response.status == 200
                submission = Submission.model_validate(await response.json())
                submission_id = submission.submissionId

                # Assert submission document.
                await self._assert_bp_submission(submission, submission_id, submission_name)

                # Assert rems.
                await self._assert_bp_rems(submission)

                # Assert datacite.
                if test_datacite:
                    assert_datacite(submission.metadata, saved=True)

                # Assert metadata objects.
                await self._assert_bp_metadata_objects(submission, object_types, sample_object_types, xml_config)

                # Assert files.
                await self._assert_bp_files(submission_id)

                created_objects = await self._list_metadata_objects(project_id, True, submission_name)

                # Test update submission (nothing changes).
                #

                # Read XML files.
                file_data = await self._read_submission_files(bp_files, datacite_files, test_datacite)

                response = await self.client.patch(
                    f"{API_PREFIX}/submit/{workflow}/{submission_id}",
                    data=file_data,
                )
                assert response.status == 200
                submission = Submission.model_validate(await response.json())

                # Assert submission document.
                await self._assert_bp_submission(submission, submission_id, submission_name)

                # Assert rems.
                await self._assert_bp_rems(submission)

                # Assert datacite.
                if test_datacite:
                    assert_datacite(submission.metadata, saved=True)

                # Assert metadata objects.
                await self._assert_bp_metadata_objects(submission, object_types, sample_object_types, xml_config)

                # Assert files.
                await self._assert_bp_files(submission_id, update=False)

                updated_objects = await self._list_metadata_objects(project_id, True, submission_name)

                def _assert_unchanged_object(_created_obj, _updated_obj):
                    assert _created_obj.objectId == _updated_obj.objectId
                    assert _created_obj.objectType == _updated_obj.objectType
                    assert _created_obj.submissionId == _updated_obj.submissionId
                    assert _created_obj.title == _updated_obj.title
                    assert _created_obj.description == _updated_obj.description
                    assert _created_obj.created == _updated_obj.created
                    assert _created_obj.modified < _updated_obj.modified

                # Assert that metadata object rows have not been changed.
                updated_object_lookup = {(o.objectType, o.name): o for o in updated_objects}
                for created_obj in created_objects:
                    updated_obj = updated_object_lookup.get((created_obj.objectType, created_obj.name))
                    assert updated_obj is not None, (
                        f"Updated '{created_obj.objectType}' metadata object '{created_obj.name}' not found"
                    )
                    _assert_unchanged_object(created_obj, updated_obj)

                # Test update submission (image changes).
                #

                # Read XML files.
                file_data = await self._read_submission_files(updated_bp_files, datacite_files, test_datacite)

                response = await self.client.patch(
                    f"{API_PREFIX}/submit/{workflow}/{submission_id}",
                    data=file_data,
                )
                assert response.status == 200
                submission = Submission.model_validate(await response.json())

                # Assert submission document.
                await self._assert_bp_submission(submission, submission_id, submission_name)

                # Assert rems.
                await self._assert_bp_rems(submission)

                # Assert datacite.
                if test_datacite:
                    assert_datacite(submission.metadata, saved=True)

                # Assert metadata objects.
                await self._assert_bp_metadata_objects(
                    submission, updated_object_types, sample_object_types, xml_config
                )

                # Assert files.
                await self._assert_bp_files(submission_id, update=True)

                updated_objects = await self._list_metadata_objects(project_id, True, submission_name)

                created_object_lookup = {(o.objectType, o.name): o for o in created_objects}
                updated_object_lookup = {(o.objectType, o.name): o for o in updated_objects}

                # Assert that non-image metadata object rows have not been changed.
                for created_obj in created_objects:
                    if created_obj.objectType != BP_IMAGE_OBJECT_TYPE:
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

    @staticmethod
    async def _read_submission_files(bp_files, datacite_files, test_datacite):
        file_data = {}
        for file in bp_files:
            file_data[file] = (BP_SUBMISSION_DIR / file).open("rb")
        if test_datacite:
            for file in datacite_files:
                file_data[file] = (DATACITE_SUBMISSION_DIR / file).open("rb")
        return file_data

    @staticmethod
    async def _assert_bp_submission(submission, submission_id, submission_name):
        assert submission.name == submission_name
        assert submission.title == "test_title"
        assert submission.description == "test_description"
        assert submission_id.startswith(generate_bp_accession_prefix(BP_DATASET_OBJECT_TYPE))

    @staticmethod
    async def _assert_bp_rems(submission):
        assert submission.rems.workflowId == 11
        assert submission.rems.organizationId == "12"

    async def _assert_bp_metadata_objects(self, expected_submission, object_types, sample_object_types, xml_config):
        project_id = expected_submission.projectId
        submission_id = expected_submission.submissionId
        submission_name = expected_submission.name

        async def _assert_xml_objects(
            response_, object_names_: dict[str, list[str]], object_ids_: dict[str, dict[str, str]]
        ) -> None:
            """Assert that all XML documents are returned."""
            assert response_.status == 200

            xml_ = await response_.read()
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
        response = await self.client.get(f"{API_PREFIX}/submissions/{submission_id}")
        assert response.status == 200
        assert expected_submission == Submission.model_validate(await response.json())

        # Retrieve both by submission id and submission name.
        for submission_id_or_name in (submission_id, submission_name):
            is_submission_name = submission_id_or_name == submission_name

            # Test list metadata objects.
            objects = await self._list_metadata_objects(project_id, is_submission_name, submission_id_or_name)
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
                response = await self.client.get(f"{docs_url}objectType={object_type}")
                # Multiple documents may be returned.
                await _assert_xml_objects(
                    response, {k: v for k, v in object_types.items() if object_type == k}, object_ids
                )

                # Test get metadata documents by schema type.
                response = await self.client.get(f"{docs_url}schemaType={schema_type}")
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
                    response = await self.client.get(f"{docs_url}objectType={object_type}&objectName={object_name}")
                    await _assert_xml_objects(response, {object_type: [object_name]}, object_ids)

                    # Test get metadata documents by object type and object id.
                    response = await self.client.get(f"{docs_url}objectType={object_type}&objectId={object_id}")
                    await _assert_xml_objects(response, {object_type: [object_name]}, object_ids)

                    # Test get metadata documents by schema type and object name.
                    response = await self.client.get(f"{docs_url}schemaType={schema_type}&objectName={object_name}")
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
                    response = await self.client.get(f"{docs_url}schemaType={schema_type}&objectId={object_id}")
                    await _assert_xml_objects(response, {object_type: [object_name]}, object_ids)

    async def _assert_bp_files(self, submission_id, update=False):
        files_url = f"{API_PREFIX}/submissions/{submission_id}/files"
        response = await self.client.get(files_url)
        assert response.status == 200
        files = Files.model_validate(await response.json()).root

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
        if not update:
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

    async def _list_metadata_objects(self, project_id, is_submission_name, submission_id_or_name):
        if is_submission_name:
            objects_url = f"{API_PREFIX}/submissions/{submission_id_or_name}/objects?projectId={project_id}"
        else:
            objects_url = f"{API_PREFIX}/submissions/{submission_id_or_name}/objects"
        response = await self.client.get(objects_url)
        assert response.status == 200
        objects = Objects.model_validate(await response.json()).objects
        return objects
