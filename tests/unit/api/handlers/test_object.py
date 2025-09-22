"""Test API endpoints from ObjectAPIHandler."""

from metadata_backend.api.models import Objects, Submission, SubmissionWorkflow
from metadata_backend.api.processors.xml.configs import (
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
    BP_SAMPLE_SET_PATH,
    BP_SAMPLE_SLIDE_OBJECT_TYPE,
    BP_SAMPLE_SPECIMEN_OBJECT_TYPE,
    BP_STAINING_OBJECT_TYPE,
    BP_SUBMISSION_OBJECT_TYPE,
)
from metadata_backend.api.processors.xml.processors import XmlDocumentProcessor, XmlObjectProcessor, XmlProcessor
from metadata_backend.api.services.accession import generate_bp_accession_prefix
from metadata_backend.conf.conf import API_PREFIX

from .common import HandlersTestCase


class ObjectHandlerTestCase(HandlersTestCase):
    """Object API endpoint class test cases."""

    async def test_submission_bp(self):
        """Test BP submission."""

        submission_dir = self.TESTFILES_ROOT / "xml" / "bp" / "submission_1"
        workflow = SubmissionWorkflow.BP.value
        project_id = self.project_id
        object_name = "1"
        xml_config = BP_FULL_SUBMISSION_XML_OBJECT_CONFIG

        files = [
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

        sample_object_types = (
            BP_SAMPLE_BIOLOGICAL_BEING_OBJECT_TYPE,
            BP_SAMPLE_SLIDE_OBJECT_TYPE,
            BP_SAMPLE_SPECIMEN_OBJECT_TYPE,
            BP_SAMPLE_BLOCK_OBJECT_TYPE,
            BP_SAMPLE_CASE_OBJECT_TYPE,
        )
        object_types = (
            BP_ANNOTATION_OBJECT_TYPE,
            BP_DATASET_OBJECT_TYPE,
            BP_IMAGE_OBJECT_TYPE,
            BP_LANDING_PAGE_OBJECT_TYPE,
            BP_OBSERVATION_OBJECT_TYPE,
            BP_OBSERVER_OBJECT_TYPE,
            BP_ORGANISATION_OBJECT_TYPE,
            BP_POLICY_OBJECT_TYPE,
            BP_REMS_OBJECT_TYPE,
            *sample_object_types,
            BP_STAINING_OBJECT_TYPE,
        )

        # Read XML files.
        data = {}
        for file in files:
            data[file] = (submission_dir / file).open("rb")

        with self.patch_verify_user_project, self.patch_verify_authorization:
            # Test create submission.
            #
            response = await self.client.post(
                f"{API_PREFIX}/workflows/{workflow}/projects/{project_id}/submissions", data=data
            )
            assert response.status == 200
            submission = Submission.model_validate(await response.json())

            # Assert submission document.
            submission_name = "test_short_name"
            submission_id = submission.submission_id
            assert submission.name == submission_name
            assert submission.title == "test_title"
            assert submission.description == "test_description"
            assert submission_id.startswith(generate_bp_accession_prefix(BP_SUBMISSION_OBJECT_TYPE))

            async def _assert_object_xml(response_, object_type_: str) -> None:
                """Assert that the XML document contains a single XML metadata object."""
                assert response_.status == 200

                xml_ = await response_.read()
                doc_processor_ = XmlDocumentProcessor(xml_config, XmlProcessor.parse_xml(xml_))

                # Assert set element.
                XmlObjectProcessor._get_xml_element(
                    xml_config.get_set_path(object_type=object_type_), doc_processor_.xml
                )

                # Assert the object root element.
                assert len(doc_processor_.xml_processors) == 1
                processor_ = doc_processor_.xml_processors[0]
                assert processor_.object_type == object_type_
                XmlObjectProcessor._get_xml_element(processor_.root_path, processor_.xml)

                # Assert object name and object id.
                assert processor_.get_xml_object_identifier().name == object_name
                object_id_ = object_id_by_type_and_name[object_type_][object_name]
                assert processor_.get_xml_object_identifier().id == object_id_

            async def _assert_sample_xmls(response_) -> None:
                """Assert that the XML document contains all sample XML metadata objects."""
                assert response_.status == 200

                xml_ = await response_.read()
                doc_processor_ = XmlDocumentProcessor(xml_config, XmlProcessor.parse_xml(xml_))

                # Assert set element.
                XmlObjectProcessor._get_xml_element(BP_SAMPLE_SET_PATH, doc_processor_.xml)

                # Assert the object root element.
                assert len(doc_processor_.xml_processors) == 5
                for processor_ in doc_processor_.xml_processors:
                    assert processor_.object_type in sample_object_types
                    assert XmlObjectProcessor._get_xml_element(processor_.root_path, processor_.xml)

                # Assert object name and object id.
                for processor_ in doc_processor_.xml_processors:
                    assert processor_.get_xml_object_identifier().name == object_name
                    object_id_ = object_id_by_type_and_name[processor_.object_type][object_name]
                    assert processor_.get_xml_object_identifier().id == object_id_

            # Test get submission document.
            #

            response = await self.client.get(f"{API_PREFIX}/submissions/{submission_id}")
            assert response.status == 200
            data = await response.json()
            assert submission == Submission.model_validate(data)

            # Retrieve both by submission id and submission name.
            for submission_id_or_name in (submission_id, submission_name):
                is_submission_name = submission_id_or_name == submission_name

                # Test list metadata objects.
                #
                if is_submission_name:
                    objects_url = f"{API_PREFIX}/submissions/{submission_id_or_name}/objects?projectId={project_id}"
                else:
                    objects_url = f"{API_PREFIX}/submissions/{submission_id_or_name}/objects"
                response = await self.client.get(objects_url)
                assert response.status == 200
                objects = Objects.model_validate(await response.json()).objects
                object_id_by_type_and_name = {o.object_type: {o.name: o.object_id} for o in objects}

                # Assert metadata object names and ids.
                for o in objects:
                    assert o.name == "1"
                    assert o.object_id.startswith(generate_bp_accession_prefix(o.object_type))

                # Assert metadata object types.
                for object_type in object_types:
                    assert 1 == sum(1 for o in objects if o.object_type == object_type)

                for object_type in object_types:
                    object_id = object_id_by_type_and_name[object_type][object_name]
                    schema_type = xml_config.get_schema_type(object_type)

                    # Test get metadata documents by object type and object name.
                    #
                    if is_submission_name:
                        docs_url = (
                            f"{API_PREFIX}/submissions/{submission_id_or_name}/objects/docs?projectId={project_id}&"
                        )
                    else:
                        docs_url = f"{API_PREFIX}/submissions/{submission_id_or_name}/objects/docs?"

                    response = await self.client.get(f"{docs_url}objectType={object_type}&objectName={object_name}")
                    await _assert_object_xml(response, object_type)

                    # Test get metadata documents by object type and object id.
                    #
                    response = await self.client.get(f"{docs_url}objectType={object_type}&objectId={object_id}")
                    await _assert_object_xml(response, object_type)

                    # Test get metadata documents by schema type and object name.
                    #
                    response = await self.client.get(f"{docs_url}schemaType={schema_type}&objectName={object_name}")
                    if object_type in sample_object_types:
                        await _assert_sample_xmls(response)
                    else:
                        await _assert_object_xml(response, object_type)

                    # Test get metadata documents by schema type and object id.
                    #
                    response = await self.client.get(f"{docs_url}schemaType={schema_type}&objectId={object_id}")
                    await _assert_object_xml(response, object_type)

                    # Test get metadata documents by object type.
                    #
                    response = await self.client.get(f"{docs_url}objectType={object_type}")
                    await _assert_object_xml(response, object_type)

                    # Test get metadata documents by schema type.
                    #
                    response = await self.client.get(f"{docs_url}schemaType={schema_type}")
                    if object_type in sample_object_types:
                        await _assert_sample_xmls(response)
                    else:
                        await _assert_object_xml(response, object_type)
