"""Test API endpoints from ObjectAPIHandler."""

import json
import uuid
from typing import Callable

from defusedxml import ElementTree

from metadata_backend.api.models import Object, Rems, SubmissionWorkflow
from metadata_backend.conf.conf import API_PREFIX

from .common import HandlersTestCase


class ObjectHandlerTestCase(HandlersTestCase):
    """Object API endpoint class test cases."""

    @staticmethod
    def assert_xml(expected: str, actual: str, remove_attr_xpath: tuple[str, str] | None = None) -> None:
        def clean_xml(xml_str):
            root = ElementTree.fromstring(xml_str)

            # Remove xmlns* attributes
            for elem in root.iter():
                elem.attrib = {k: v for k, v in elem.attrib.items() if not k.startswith("xmlns")}

            # Remove specific attribute at a given XPath
            if remove_attr_xpath:
                xpath, attr_name = remove_attr_xpath
                for target in root.findall(xpath):
                    if attr_name in target.attrib:
                        del target.attrib[attr_name]

            return root

        cleaned_expected = ElementTree.tostring(clean_xml(expected))
        cleaned_actual = ElementTree.tostring(clean_xml(actual))

        assert cleaned_expected == cleaned_actual

    @staticmethod
    def change_xml_attribute(xml: str, xpath: str, attribute: str, new_value: str) -> str:
        root = ElementTree.fromstring(xml)
        for elem in root.findall(xpath):
            if attribute in elem.attrib:
                elem.attrib[attribute] = new_value
        return ElementTree.tostring(root, encoding="unicode")

    async def test_post_get_delete_xml_object(self):
        """Test that creating, modifying and deleting XML metadata object works."""

        bp_files = [
            ("bpannotation", "annotation.xml", (".//ANNOTATION", "alias"), (".//ANNOTATION", "accession")),
            ("bpobservation", "observation.xml", (".//OBSERVATION", "alias"), (".//OBSERVATION", "accession")),
            # TODO(improve): test all BP XML files
        ]

        fega_files = [
            ("policy", "policy.xml", (".//POLICY", "alias"), (".//POLICY", "accession")),
            # TODO(improve): test all FEGA XML files
        ]

        workflow_files = {
            SubmissionWorkflow.BP: bp_files,
            SubmissionWorkflow.FEGA: fega_files,
        }

        for workflow in {SubmissionWorkflow.BP, SubmissionWorkflow.FEGA}:
            submission_id = await self.post_submission(workflow=workflow.value)

            files = workflow_files[workflow]

            with (
                self.patch_verify_user_project,
                self.patch_verify_authorization,
            ):
                for schema, file_name, alias_xpath, accession_xpath in files:
                    xml_document = self.read_metadata_object(schema, file_name)

                    alias = f"alias-{uuid.uuid4()}"
                    xml_document = self.change_xml_attribute(xml_document, *alias_xpath, alias)

                    # Create metadata object with content type auto-detection.

                    response = await self.client.post(
                        f"{API_PREFIX}/objects/{schema}", params={"submission": submission_id}, data=xml_document
                    )
                    assert response.status == 201
                    result = await response.json()
                    assert result[0]["alias"] == alias
                    assert "accessionId" in result[0]

                    accession_id = result[0]["accessionId"]

                    # Read metadata object as xml.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                        headers={"Content-Type": "application/xml"},
                        data=xml_document,
                    )
                    assert response.status == 200
                    self.assert_xml(xml_document, await response.text(), accession_xpath)

                    # Read metadata object as json.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                        headers={"Content-Type": "application/json"},
                    )
                    assert response.status == 200
                    assert (await response.json())["accessionId"] == accession_id

                    # Read metadata object as json (default content type).

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                    )
                    assert response.status == 200
                    assert (await response.json())["accessionId"] == accession_id

                    # Read metadata object ids.

                    response = await self.client.get(f"{API_PREFIX}/objects/{schema}?submission={submission_id}")
                    assert response.status == 200
                    assert Object(object_id=accession_id, submission_id=submission_id, schema_type=schema) == Object(
                        **(await response.json())[0]
                    )

                    # Update metadata object (put) without content type auto-detection.

                    alias = f"alias-{uuid.uuid4()}"  # Changing alias as its updated is allowed.
                    xml_document = self.change_xml_attribute(xml_document, *alias_xpath, alias)

                    response = await self.client.put(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                        headers={"Content-Type": "application/xml"},
                        data=xml_document,
                    )
                    assert response.status == 200
                    result = await response.json()
                    assert result["accessionId"] == accession_id

                    # Read metadata object as xml.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                        headers={"Content-Type": "application/xml"},
                    )
                    assert response.status == 200
                    self.assert_xml(xml_document, await response.text(), accession_xpath)

                    # Update metadata object (patch) with content type auto-detection.

                    alias = f"alias-{uuid.uuid4()}"  # Changing alias as its updated is allowed.
                    xml_document = self.change_xml_attribute(xml_document, *alias_xpath, alias)

                    response = await self.client.patch(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}", data=xml_document
                    )
                    assert response.status == 200
                    result = await response.json()
                    assert result["accessionId"] == accession_id

                    # Read metadata object as xml.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                        headers={"Content-Type": "application/xml"},
                    )
                    assert response.status == 200
                    self.assert_xml(xml_document, await response.text(), accession_xpath)

                    # Delete metadata object

                    response = await self.client.delete(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                    )
                    assert response.status == 204

                    # Read metadata object.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                    )
                    assert response.status == 404

    async def test_post_get_delete_json_object(self):
        """Test that creating, modifying and deleting JSON metadata object works."""

        bp_files = [
            ("bpannotation", "annotation.json"),
            ("bpobserver", "observer.json"),
            # TODO(improve): test all BP JSON files
        ]

        fega_files = [
            ("dataset", "dataset.json"),
            # TODO(improve): test all FEGA JSON files
        ]

        workflow_files = {
            SubmissionWorkflow.BP: bp_files,
            SubmissionWorkflow.FEGA: fega_files,
        }

        alias_callback = lambda d, val: {**d, "alias": val}

        def update_json_field(json_str: str, val: str, update_callback: Callable[[dict, str], dict]) -> str:
            return json.dumps(update_callback(json.loads(json_str), val))

        for workflow in {SubmissionWorkflow.BP, SubmissionWorkflow.FEGA}:
            submission_id = await self.post_submission(workflow=workflow.value)

            files = workflow_files[workflow]

            with (
                self.patch_verify_user_project,
                self.patch_verify_authorization,
            ):
                for schema, file_name in files:
                    json_document = self.read_metadata_object(schema, file_name)

                    alias = f"alias-{uuid.uuid4()}"
                    json_document = update_json_field(json_document, alias, alias_callback)

                    # Create metadata object with content type auto-detection.

                    response = await self.client.post(
                        f"{API_PREFIX}/objects/{schema}", params={"submission": submission_id}, data=json_document
                    )
                    assert response.status == 201
                    result = await response.json()
                    assert result[0]["alias"] == alias
                    assert "accessionId" in result[0]

                    accession_id = result[0]["accessionId"]

                    # Read metadata object as json.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                        headers={"Content-Type": "application/json"},
                    )
                    assert response.status == 200
                    result = await response.json()
                    assert {**json.loads(json_document), "accessionId": accession_id} == result

                    # Read metadata object as json (default content type).

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                    )
                    assert response.status == 200
                    result = await response.json()
                    assert {**json.loads(json_document), "accessionId": accession_id} == result

                    # Read metadata object ids.

                    response = await self.client.get(f"{API_PREFIX}/objects/{schema}?submission={submission_id}")
                    assert response.status == 200
                    assert Object(object_id=accession_id, submission_id=submission_id, schema_type=schema) == Object(
                        **(await response.json())[0]
                    )

                    # Update metadata object (put) without content type auto-detection.

                    alias = f"alias-{uuid.uuid4()}"  # Changing alias as its update is allowed.
                    json_document = update_json_field(json_document, alias, alias_callback)

                    response = await self.client.put(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                        headers={"Content-Type": "application/json"},
                        data=json_document,
                    )
                    assert response.status == 200
                    result = await response.json()
                    assert result["accessionId"] == accession_id

                    # Read metadata object as json.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                    )
                    assert response.status == 200
                    result = await response.json()
                    assert {**json.loads(json_document), "accessionId": accession_id} == result

                    # Update metadata object (patch) with content type auto-detection.

                    alias = f"alias-{uuid.uuid4()}"  # Changing alias as its update is allowed.
                    json_document = update_json_field(json_document, alias, alias_callback)

                    response = await self.client.patch(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}", data=json_document
                    )
                    assert response.status == 200
                    result = await response.json()
                    assert result["accessionId"] == accession_id

                    # Read metadata object as json.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                    )
                    assert response.status == 200
                    result = await response.json()
                    assert {**json.loads(json_document), "accessionId": accession_id} == result

                    # Delete metadata object

                    response = await self.client.delete(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                    )
                    assert response.status == 204

                    # Read metadata object.

                    response = await self.client.get(
                        f"{API_PREFIX}/objects/{schema}/{accession_id}",
                    )
                    assert response.status == 404

    async def test_post_invalid_json_object(self):
        """Test posting invalid JSON metadata object."""

        workflow = SubmissionWorkflow.FEGA
        schema = "dataset"
        submission_id = await self.post_submission(workflow=workflow.value)

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.post(
                f"{API_PREFIX}/objects/{schema}", params={"submission": submission_id}, data="invalid"
            )
            assert response.status == 400
            assert "Invalid JSON payload" in await response.text()

    async def test_post_invalid_xml_object(self):
        """Test posting invalid XML metadata object."""

        workflow = SubmissionWorkflow.FEGA
        schema = "dataset"
        submission_id = await self.post_submission(workflow=workflow.value)

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.post(
                f"{API_PREFIX}/objects/{schema}",
                params={"submission": submission_id},
                headers={"Content-Type": "application/xml"},
                data="invalid",
            )
            assert response.status == 400
            assert "not valid" in await response.text()

    async def test_post_invalid_schema(self):
        """Test posting invalid metadata object schema."""

        workflow = SubmissionWorkflow.BP
        schema = "invalid"
        submission_id = await self.post_submission(workflow=workflow.value)

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            response = await self.client.post(
                f"{API_PREFIX}/objects/{schema}", params={"submission": submission_id}, data="invalid"
            )
            assert response.status == 400
            assert "does not support" in await response.text()

    async def test_post_bp_xml_rems(self):
        """Test that creating BP REMS XML works."""
        submission_id = await self.post_submission(workflow=SubmissionWorkflow.BP.value)
        schema = "bprems"
        xml_document = self.read_metadata_object(schema, "rems.xml")

        with (
            self.patch_verify_user_project,
            self.patch_verify_authorization,
        ):
            # Post BP REMS.
            response = await self.client.post(
                f"{API_PREFIX}/objects/{schema}", params={"submission": submission_id}, data=xml_document
            )
            self.assertEqual(response.status, 201)

            # Verify that REMS was added to the submission.
            response = await self.client.get(f"{API_PREFIX}/submissions/{submission_id}")
            self.assertEqual(response.status, 200)
            submission = await response.json()
            rems = Rems(**submission["rems"])
            assert rems.workflow_id == 1, "'workflowId' is not 1"
            assert rems.organization_id == "CSC", "'organizationId' is not CSC"
            assert rems.licenses == []
