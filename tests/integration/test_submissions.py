"""Test operations with submissions."""

import aiohttp
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime

from tests.integration.conf import drafts_url, objects_url, publish_url, submit_url, testfiles_root
from tests.integration.helpers import (
    add_submission_linked_folder,
    check_dataset_accession_ids,
    check_file_accession_ids,
    create_multi_file_request_data,
    create_request_data,
    create_request_json_data,
    create_submission,
    delete_object,
    delete_published_submission,
    delete_submission,
    get_draft,
    get_object,
    get_submission,
    get_user_data,
    patch_submission_doi,
    patch_submission_rems,
    post_data_ingestion,
    post_draft,
    post_object,
    post_object_json,
    post_submission,
    publish_submission,
    setup_files_for_ingestion,
    submissions_url,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestSubmissions:
    """Test querying submissions and their objects."""

    async def test_get_submissions(self, client_logged_in, submission_fega: str, project_id: str):
        """Test submissions REST API GET .

        :param client_logged_in: HTTP client in which request call is made
        :param submission_fega: id of the submission used to group submission objects
        :param project_id: id of the project the submission belongs to
        """
        async with client_logged_in.get(f"{submissions_url}?projectId={project_id}") as resp:
            LOG.debug("Reading submission %s", submission_fega)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            response = await resp.json()
            assert len(response["submissions"]) == 1, response
            assert response["page"] == {
                "page": 1,
                "size": 5,
                "totalPages": 1,
                "totalSubmissions": 1,
            }
            assert response["submissions"][0]["submissionId"] == submission_fega

    async def test_get_submissions_objects(self, client_logged_in, submission_fega: str, project_id: str):
        """Test submissions REST API GET with objects.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_fega: id of the submission used to group submission objects
        :param project_id: id of the project the submission belongs to
        """
        accession_id = await post_object_json(client_logged_in, "study", submission_fega, "SRP000539.json")
        async with client_logged_in.get(f"{submissions_url}?projectId={project_id}") as resp:
            LOG.debug("Reading submission %s", submission_fega)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            response = await resp.json()
            assert len(response["submissions"]) == 1
            assert response["submissions"][0]["metadataObjects"][0]["accessionId"] == accession_id
            assert "tags" in response["submissions"][0]["metadataObjects"][0]
            assert response["submissions"][0]["metadataObjects"][0]["tags"]["submissionType"] == "Form"

        await delete_object(client_logged_in, "study", accession_id)

    async def test_submissions_work(self, client_logged_in, submission_fega):
        """Test actions in submission XML files.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_fega: id of the submission used to group submission objects
        """
        # Post original submission with two 'add' actions
        sub_files = [
            ("submission", "ERA521986_valid.xml"),
            ("study", "SRP000539.xml"),
            ("sample", "SRS001433.xml"),
        ]
        submission_data = await create_multi_file_request_data(sub_files)

        async with client_logged_in.post(
            f"{submit_url}/FEGA", params={"submission": submission_fega}, data=submission_data
        ) as resp:
            LOG.debug("Checking initial submission worked")
            res = await resp.json()
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}: {res}"
            assert len(res) == 2, "expected 2 objects"
            assert res[0]["schema"] == "study", "expected first element to be study"
            assert res[1]["schema"] == "sample", "expected second element to be sample"
            study_access_id = res[0]["accessionId"]
            sample_access_id = res[1]["accessionId"]

        # Sanity check that the study object was inserted correctly before modifying it
        async with client_logged_in.get(f"{objects_url}/study/{study_access_id}") as resp:
            LOG.debug("Sanity checking that previous object was added correctly")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            assert res["accessionId"] == study_access_id, "study accession id does not match"
            assert res["alias"] == "GSE10966", "study alias does not match"
            assert res["descriptor"]["studyTitle"] == (
                "Highly integrated epigenome maps in Arabidopsis - whole genome shotgun bisulfite sequencing"
            ), "study title does not match"
            # metax_id = res.get("metaxIdentifier", None)
            # doi = res.get("doi", None)
            # assert metax_id is not None
            # assert doi is not None

        # check that objects are added to submission
        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_fega)
            res = await resp.json()
            expected_study = {
                "accessionId": study_access_id,
                "schema": "study",
                "tags": {
                    "submissionType": "XML",
                    "displayTitle": (
                        "Highly integrated epigenome maps in Arabidopsis - whole genome shotgun bisulfite sequencing"
                    ),
                    "fileName": "SRP000539.xml",
                },
            }
            assert expected_study in res["metadataObjects"], "submission metadataObjects content mismatch"
            expected_sample = {
                "accessionId": sample_access_id,
                "schema": "sample",
                "tags": {
                    "submissionType": "XML",
                    "displayTitle": "HapMap sample from Homo sapiens",
                    "fileName": "SRS001433.xml",
                },
            }
            assert expected_sample in res["metadataObjects"], "submission metadataObjects content mismatch"

        # Give test file the correct accession id
        LOG.debug("Sharing the correct accession ID created in this test instance")
        mod_study = testfiles_root / "study" / "SRP000539_modified.xml"
        tree = ET.parse(mod_study)
        root = tree.getroot()
        for elem in root.iter("STUDY"):
            elem.set("accession", study_access_id)
        tree.write(mod_study, encoding="utf-8")

        # Post new submission that modifies previously added study object and validates it
        sub_files = [
            ("submission", "ERA521986_modify.xml"),
            ("study", "SRP000539_modified.xml"),
        ]
        more_submission_data = await create_multi_file_request_data(sub_files)
        async with client_logged_in.post(f"{submit_url}/FEGA", data=more_submission_data) as resp:
            LOG.debug("Checking object in initial submission was modified")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            assert len(res) == 2, "expected 2 objects"
            new_study_access_id = res[0]["accessionId"]
            assert study_access_id == new_study_access_id

        # Check the modified object was inserted correctly
        async with client_logged_in.get(f"{objects_url}/study/{new_study_access_id}") as resp:
            LOG.debug("Checking that previous object was modified correctly")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            assert res["accessionId"] == new_study_access_id, "study accession id does not match"
            assert res["alias"] == "GSE10966", "study alias does not match"
            assert res["descriptor"]["studyTitle"] == (
                "Different title for testing purposes"
            ), "updated study title does not match"
            # assert res["metaxIdentifier"] == metax_id
            # assert res["doi"] == doi

        # check that study is updated to submission
        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_fega)
            res = await resp.json()
            expected_study = {
                "accessionId": study_access_id,
                "schema": "study",
                "tags": {
                    "submissionType": "XML",
                    "displayTitle": "Different title for testing purposes",
                    "fileName": "SRP000539_modified.xml",
                },
            }
            assert expected_study in res["metadataObjects"], "submission metadataObjects content mismatch"

        await delete_object(client_logged_in, "sample", sample_access_id)
        await delete_object(client_logged_in, "study", study_access_id)

        # Remove the accession id that was used for testing from test file
        LOG.debug("Sharing the correct accession ID created in this test instance")
        mod_study = testfiles_root / "study" / "SRP000539_modified.xml"
        tree = ET.parse(mod_study)
        root = tree.getroot()
        for elem in root.iter("STUDY"):
            del elem.attrib["accession"]
        tree.write(mod_study, encoding="utf-8")
        with open(mod_study, "a") as f:
            f.write("\n")


class TestSubmissionOperations:
    """Testing basic CRUD submission operations."""

    async def test_crud_submissions_works(self, client_logged_in, project_id):
        """Test submissions REST api POST, GET, PATCH, PUBLISH and DELETE reqs.

        :param client_logged_in: HTTP client in which request call is made
        :param project_id: id of the project the submission belongs to
        """
        # Create new submission and check its creation succeeded
        submission_data = {
            "name": "Mock Submission",
            "description": "Mock Base submission to submission ops",
            "projectId": project_id,
            "workflow": "FEGA",
        }
        submission_fega = await post_submission(client_logged_in, submission_data)
        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug("Checking that submission %s was created", submission_fega)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Try creating the same submission again and check that it fails
        async with client_logged_in.post(f"{submissions_url}", data=json.dumps(submission_data)) as resp:
            ans = await resp.json()
            assert resp.status == 400, f"HTTP Status code error {resp.status} {ans}"
            assert ans["detail"] == f"Submission with name 'Mock Submission' already exists in project {project_id}"

        # Create draft from test XML file and patch the draft into the newly created submission
        draft_id = await post_draft(client_logged_in, "sample", submission_fega, "SRS001433.xml")
        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_fega)
            res = await resp.json()
            assert res["submissionId"] == submission_fega, "expected submission id does not match"
            assert res["name"] == submission_data["name"], "expected submission name does not match"
            assert res["description"] == submission_data["description"], "submission description content mismatch"
            assert res["published"] is False, "submission is published, expected False"
            assert res["drafts"] == [
                {
                    "accessionId": draft_id,
                    "schema": "draft-sample",
                    "tags": {
                        "submissionType": "XML",
                        "displayTitle": "HapMap sample from Homo sapiens",
                        "fileName": "SRS001433.xml",
                    },
                }
            ], f'submission drafts content mismatch, {res["drafts"]}'
            assert res["metadataObjects"] == [], "there are objects in submission, expected empty"

        # Get the draft from the collection within this client and post it to objects collection
        draft_data = await get_draft(client_logged_in, "sample", draft_id)
        async with client_logged_in.post(
            f"{objects_url}/sample",
            params={"submission": submission_fega},
            data=draft_data,
        ) as resp:
            LOG.debug("Adding draft to actual objects")
            assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
            ans = await resp.json()
            assert ans["accessionId"] != draft_id, "draft id does not match expected"
            accession_id = ans["accessionId"]

        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_fega)
            res = await resp.json()
            assert res["submissionId"] == submission_fega, "expected submission id does not match"
            assert res["published"] is False, "submission is published, expected False"
            assert "datePublished" not in res.keys()
            assert res["drafts"] == [
                {
                    "accessionId": draft_id,
                    "schema": "draft-sample",
                    "tags": {
                        "submissionType": "XML",
                        "displayTitle": "HapMap sample from Homo sapiens",
                        "fileName": "SRS001433.xml",
                    },
                }
            ], f'submission drafts content mismatch, {res["drafts"]}'
            assert res["metadataObjects"] == [
                {
                    "accessionId": accession_id,
                    "schema": "sample",
                    "tags": {
                        "submissionType": "Form",
                        "displayTitle": "HapMap sample from Homo sapiens",
                    },
                }
            ], "submission metadataObjects content mismatch"

        # Add DOI for publishing the submission
        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        await patch_submission_doi(client_logged_in, submission_fega, doi_data_raw)

        # Add a study and dataset for publishing a submission
        ds_1 = await post_object(client_logged_in, "dataset", submission_fega, "dataset.xml")

        study = await post_object_json(client_logged_in, "study", submission_fega, "SRP000539.json")

        ds_2 = await post_object(client_logged_in, "dataset", submission_fega, "dataset_put.xml")

        rems_data = await create_request_json_data("dac", "dac_rems.json")
        await patch_submission_rems(client_logged_in, submission_fega, rems_data)
        await post_object_json(client_logged_in, "policy", submission_fega, "policy.json")
        await post_object_json(client_logged_in, "run", submission_fega, "ERR000076.json")

        submission_fega = await publish_submission(client_logged_in, submission_fega)
        ds_1 = await get_object(client_logged_in, "dataset", ds_1[0])
        study = await get_object(client_logged_in, "study", study)
        ds_2 = await get_object(client_logged_in, "dataset", ds_2[0])

        # Check the draft was deleted after publication
        await get_draft(client_logged_in, "sample", draft_id, 404)

        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_fega)
            res = await resp.json()
            assert res["submissionId"] == submission_fega, "expected submission id does not match"
            assert res["published"] is True, "submission is not published, expected True"
            assert "datePublished" in res.keys()
            assert "extraInfo" in res.keys()
            assert res["drafts"] == [], "there are drafts in submission, expected empty"
            assert len(res["metadataObjects"]) == 6, "submission metadataObjects content mismatch"
            assert "rems" in res.keys(), "submission does not have rems dac data"

        # Check that submission info and its objects cannot be updated and that publishing it again fails
        async with client_logged_in.patch(
            f"{submissions_url}/{submission_fega}", data=json.dumps({"name": "new_name"})
        ) as resp:
            LOG.debug("Trying to update submission values")
            assert resp.status == 405, f"HTTP Status code error, got {resp.status}"
        async with client_logged_in.patch(
            f"{objects_url}/sample/{accession_id}", params={"submission": submission_fega}, json={}
        ) as resp:
            LOG.debug("Trying to update submission objects")
            assert resp.status == 405, f"HTTP Status code error, got {resp.status}"
        async with client_logged_in.patch(f"{publish_url}/{submission_fega}") as resp:
            LOG.debug("Trying to re-publish submission %s", submission_fega)
            assert resp.status == 405, f"HTTP Status code error, got {resp.status}"

        # Check submission objects cannot be replaced
        sample = await create_request_data("sample", "SRS001433.xml")
        async with client_logged_in.put(
            f"{objects_url}/sample/{accession_id}", params={"submission": submission_fega}, data=sample
        ) as resp:
            LOG.debug("Trying to replace submission objects")
            assert resp.status == 405, f"HTTP Status code error, got {resp.status}"
        async with client_logged_in.put(f"{submissions_url}/{submission_fega}/doi", data=doi_data_raw) as resp:
            LOG.debug("Trying to replace submission doi")
            assert resp.status == 405, f"HTTP Status code error {resp.status} {ans}"
        async with client_logged_in.put(f"{submissions_url}/{submission_fega}/rems", data=rems_data) as resp:
            LOG.debug("Trying to replace submission rems")
            assert resp.status == 405, f"HTTP Status code error {resp.status} {ans}"

        # Check new drafts or objects cannot be added under published submission
        run = await create_request_json_data("run", "ERR000076.json")
        async with client_logged_in.post(f"{drafts_url}/run", params={"submission": submission_fega}, data=run) as resp:
            LOG.debug("Trying to add draft object to already published submission")
            assert resp.status == 405, f"HTTP Status code error, got {resp.status}"
        async with client_logged_in.post(
            f"{objects_url}/run", params={"submission": submission_fega}, data=run
        ) as resp:
            LOG.debug("Trying to add object to already published submission")
            assert resp.status == 405, f"HTTP Status code error, got {resp.status}"

        # Below should be adapted to PID ms when possible: currently not possible to retrieve existing DOIs

        # Check that datacite has references between datasets and study
        # async with client_logged_in.get(f"{datacite_url}/dois/{ds_1['doi']}") as datacite_resp:
        #     assert datacite_resp.status == 200, f"HTTP Status code error, got {datacite_resp.status}"
        #     datacite_res = await datacite_resp.json()
        #     ds_1 = datacite_res
        # async with client_logged_in.get(f"{datacite_url}/dois/{ds_2['doi']}") as datacite_resp:
        #     assert datacite_resp.status == 200, f"HTTP Status code error, got {datacite_resp.status}"
        #     datacite_res = await datacite_resp.json()
        #     ds_2 = datacite_res
        # async with client_logged_in.get(f"{datacite_url}/dois/{study['doi']}") as datacite_resp:
        #     assert datacite_resp.status == 200, f"HTTP Status code error, got {datacite_resp.status}"
        #     datacite_res = await datacite_resp.json()
        #     study = datacite_res
        # assert ds_1["data"]["attributes"]["relatedIdentifiers"][0]["relatedIdentifier"] == study["id"]
        # assert ds_2["data"]["attributes"]["relatedIdentifiers"][0]["relatedIdentifier"] == study["id"]
        # for id in study["data"]["attributes"]["relatedIdentifiers"]:
        #     assert id["relatedIdentifier"] in {ds_1["id"], ds_2["id"]}

        # Attempt deleting submission
        await delete_published_submission(client_logged_in, submission_fega)

    async def test_crud_submissions_works_no_publish(self, client_logged_in, project_id):
        """Test submissions REST API POST, GET, PATCH, PUBLISH and DELETE reqs.

        :param client_logged_in: HTTP client in which request call is made
        :param project_id: id of the project the submission belongs to
        """
        # Create new submission and check its creation succeeded
        submission_data = {
            "name": "Mock Unpublished submission",
            "description": "test umpublished submission",
            "projectId": project_id,
            "workflow": "FEGA",
        }
        submission_fega = await post_submission(client_logged_in, submission_data)
        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug("Checking that submission %s was created", submission_fega)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Create draft from test XML file and patch the draft into the newly created submission
        draft_id = await post_draft(client_logged_in, "sample", submission_fega, "SRS001433.xml")
        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_fega)
            res = await resp.json()
            assert res["submissionId"] == submission_fega, "expected submission id does not match"
            assert res["name"] == submission_data["name"], "expected submission name does not match"
            assert res["description"] == submission_data["description"], "submission description content mismatch"
            assert res["published"] is False, "submission is published, expected False"
            assert res["drafts"] == [
                {
                    "accessionId": draft_id,
                    "schema": "draft-sample",
                    "tags": {
                        "submissionType": "XML",
                        "displayTitle": "HapMap sample from Homo sapiens",
                        "fileName": "SRS001433.xml",
                    },
                }
            ], "submission drafts content mismatch"
            assert res["metadataObjects"] == [], "there are objects in submission, expected empty"

        # Get the draft from the collection within this client and post it to objects collection
        draft = await get_draft(client_logged_in, "sample", draft_id)
        async with client_logged_in.post(
            f"{objects_url}/sample", params={"submission": submission_fega}, data=draft
        ) as resp:
            LOG.debug("Adding draft to actual objects")
            assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
            ans = await resp.json()
            assert ans["accessionId"] != draft_id, "draft id does not match expected"
            accession_id = ans["accessionId"]

        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_fega)
            res = await resp.json()
            assert res["submissionId"] == submission_fega, "expected submission id does not match"
            assert res["published"] is False, "submission is published, expected False"
            assert res["drafts"] == [
                {
                    "accessionId": draft_id,
                    "schema": "draft-sample",
                    "tags": {
                        "submissionType": "XML",
                        "displayTitle": "HapMap sample from Homo sapiens",
                        "fileName": "SRS001433.xml",
                    },
                }
            ], "submission drafts content mismatch"
            assert res["metadataObjects"] == [
                {
                    "accessionId": accession_id,
                    "schema": "sample",
                    "tags": {
                        "submissionType": "Form",
                        "displayTitle": "HapMap sample from Homo sapiens",
                    },
                }
            ], "submission metadataObjects content mismatch"

        # Delete submission
        await delete_submission(client_logged_in, submission_fega)
        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug("Checking that submission %s was deleted", submission_fega)
            assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

    async def test_adding_doi_info_to_submission_works(self, client_logged_in, project_id):
        """Test that proper DOI info can be added to submission and bad DOI info cannot be.

        :param client_logged_in: HTTP client in which request call is made
        :param project_id: id of the project the submission belongs to
        """
        # Create new submission and check its creation succeeded
        submission_data = {
            "name": "DOI Submission",
            "description": "Mock Base submission for adding DOI info",
            "projectId": project_id,
            "workflow": "FEGA",
        }
        submission_fega = await post_submission(client_logged_in, submission_data)
        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug("Checking that submission %s was created", submission_fega)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Get correctly formatted DOI info and patch it into the new submission successfully
        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        doi_data = json.loads(doi_data_raw)
        await patch_submission_doi(client_logged_in, submission_fega, doi_data_raw)

        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_fega)
            res = await resp.json()
            assert res["submissionId"] == submission_fega, "expected submission id does not match"
            assert res["name"] == submission_data["name"], "expected submission name does not match"
            assert res["description"] == submission_data["description"], "submission description content mismatch"
            assert res["published"] is False, "submission is published, expected False"
            assert res["doiInfo"] == doi_data, "submission doi does not match"

        # Test that an incomplete DOI object fails to patch into the submission
        put_bad_doi = {"identifier": {}}
        async with client_logged_in.patch(
            f"{submissions_url}/{submission_fega}/doi", data=json.dumps(put_bad_doi)
        ) as resp:
            LOG.debug("Tried updating submission %s", submission_fega)
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            assert (
                res["detail"] == "Provided input does not seem correct for field: 'doiInfo'"
            ), "expected error mismatch"

        # Check the existing DOI info is not altered
        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug("Checking that submission %s was not patched with bad DOI", submission_fega)
            res = await resp.json()
            assert res["doiInfo"] == doi_data, "submission doi does not match"

        # Test that extraInfo cannot be altered
        patch_add_bad_doi = [{"op": "add", "path": "/extraInfo", "value": {"publisher": "something"}}]
        async with client_logged_in.patch(
            f"{submissions_url}/{submission_fega}", data=json.dumps(patch_add_bad_doi)
        ) as resp:
            LOG.debug("Tried updating submission %s", submission_fega)
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            detail = res["detail"]
            assert (
                detail == "Patch submission operation should be provided as a JSON object"
            ), f"error mismatch, got '{detail}'"

        # Delete submission
        await delete_submission(client_logged_in, submission_fega)
        async with client_logged_in.get(f"{submissions_url}/{submission_fega}") as resp:
            LOG.debug("Checking that submission %s was deleted", submission_fega)
            assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

    async def test_linking_folder_to_submission_works(self, client_logged_in, project_id):
        """Test that a folder name can be linked to a submission.

        :param client_logged_in: HTTP client in which request call is made
        :param project_id: id of the project the submission belongs to
        """
        # Create new submission and check its creation succeeded
        submission_data = {
            "name": "Test submission",
            "description": "Mock a submission for linked folder test",
            "projectId": project_id,
            "workflow": "SDSX",
        }

        submission_id = await post_submission(client_logged_in, submission_data)
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was created", submission_id)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Test linking a folder, removing it, linking another
        test_names = ["foldername", "", "foldername2"]

        for name in test_names:
            await add_submission_linked_folder(client_logged_in, submission_id, name)
            submission = await get_submission(client_logged_in, submission_id)
            assert submission["linkedFolder"] == name

    async def test_adding_rems_info_to_submission_works(self, client_logged_in, project_id):
        """Test that correct REMS info can be added to submission and invalid REMS info will raise error.

        :param client_logged_in: HTTP client in which request call is made
        :param project_id: id of the project the submission belongs to
        """
        # Create new submission and check its creation succeeded
        submission_data = {
            "name": "REMS Submission",
            "description": "Mock Base submission for adding REMS info",
            "projectId": project_id,
            "workflow": "SDSX",
        }
        submission_sdsx = await post_submission(client_logged_in, submission_data)
        async with client_logged_in.get(f"{submissions_url}/{submission_sdsx}") as resp:
            LOG.debug("Checking that submission %s was created", submission_sdsx)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Get correctly formatted REMS info and patch it into the new submission successfully
        rems_data_raw = await create_request_json_data("dac", "dac_rems.json")
        rems_data = json.loads(rems_data_raw)
        await patch_submission_rems(client_logged_in, submission_sdsx, rems_data_raw)

        async with client_logged_in.get(f"{submissions_url}/{submission_sdsx}") as resp:
            LOG.debug("Checking that submission %s was patched", submission_sdsx)
            res = await resp.json()
            assert res["submissionId"] == submission_sdsx, "expected submission id does not match"
            assert res["name"] == submission_data["name"], "expected submission name does not match"
            assert res["description"] == submission_data["description"], "submission description content mismatch"
            assert res["published"] is False, "submission is published, expected False"
            assert res["rems"] == rems_data, "rems info does not match"

        # Test that an incorrect REMS object fails to patch into the submission
        # error case: REMS's licenses do not include DAC's linked license
        put_bad_rems = {"workflowId": 1, "organizationId": "CSC", "licenses": [2, 3]}
        async with client_logged_in.patch(
            f"{submissions_url}/{submission_sdsx}/rems", data=json.dumps(put_bad_rems)
        ) as resp:
            LOG.debug("Tried updating submission %s", submission_sdsx)
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            assert (
                res["detail"] == "Rems error: Linked license '1' doesn't exist in licenses '[2, 3]'"
            ), "expected error mismatch"


class TestSubmissionPagination:
    """Testing getting submissions, draft submissions with pagination."""

    async def test_getting_paginated_submissions(self, client_logged_in, project_id):
        """Check that /submissions returns submissions with correct pagination.

        :param client_logged_in: HTTP client in which request call is made
        :param project_id: id of the project the submission belongs to
        """
        submissions = []
        for number in range(0, 9):
            submission_data = {
                "name": f"Submission {number}",
                "description": "Submission description {number}",
                "projectId": project_id,
                "workflow": "FEGA",
            }
            submissions.append(await post_submission(client_logged_in, submission_data))

        for submission_fega in submissions[6:9]:
            await post_object_json(client_logged_in, "study", submission_fega, "SRP000539.json")
            doi_data_raw = await create_request_json_data("doi", "test_doi.json")
            await patch_submission_doi(client_logged_in, submission_fega, doi_data_raw)
            rems_data = await create_request_json_data("dac", "dac_rems.json")
            await patch_submission_rems(client_logged_in, submission_fega, rems_data)
            await post_object_json(client_logged_in, "policy", submission_fega, "policy.json")
            await post_object_json(client_logged_in, "run", submission_fega, "ERR000076.json")
            await post_object_json(client_logged_in, "dataset", submission_fega, "dataset.json")
            await publish_submission(client_logged_in, submission_fega)

        # Test default values
        async with client_logged_in.get(f"{submissions_url}?projectId={project_id}") as resp:
            # The submissions received here are from previous
            # tests where the submissions were not deleted
            assert resp.status == 200
            ans = await resp.json()
            assert ans["page"]["page"] == 1, ans["page"]["page"]
            assert ans["page"]["size"] == 5, ans["page"]["size"]
            assert ans["page"]["totalPages"] == 2, ans["page"]["totalPages"]
            assert ans["page"]["totalSubmissions"] == 9, ans["page"]["totalSubmissions"]
            assert len(ans["submissions"]) == 5, len(ans["submissions"])

        # Test with custom pagination values
        async with client_logged_in.get(f"{submissions_url}?page=2&per_page=3&projectId={project_id}") as resp:
            assert resp.status == 200
            ans = await resp.json()
            assert ans["page"]["page"] == 2, ans["page"]["page"]
            assert ans["page"]["size"] == 3, ans["page"]["size"]
            assert ans["page"]["totalPages"] == 3, ans["page"]["totalPages"]
            assert ans["page"]["totalSubmissions"] == 9, ans["page"]["totalSubmissions"]
            assert len(ans["submissions"]) == 3, len(ans["submissions"])

        # Test querying only published submissions
        async with client_logged_in.get(f"{submissions_url}?published=true&projectId={project_id}") as resp:
            assert resp.status == 200
            ans = await resp.json()
            assert ans["page"]["page"] == 1, ans["page"]["page"]
            assert ans["page"]["size"] == 5, ans["page"]["size"]
            assert ans["page"]["totalPages"] == 1, ans["page"]["totalPages"]
            assert ans["page"]["totalSubmissions"] == 3, ans["page"]["totalSubmissions"]
            assert len(ans["submissions"]) == 3, len(ans["submissions"])

        # Test querying only draft submissions
        async with client_logged_in.get(f"{submissions_url}?published=false&projectId={project_id}") as resp:
            assert resp.status == 200
            ans = await resp.json()
            assert ans["page"]["page"] == 1, ans["page"]["page"]
            assert ans["page"]["size"] == 5, ans["page"]["size"]
            assert ans["page"]["totalPages"] == 2, ans["page"]["totalPages"]
            assert ans["page"]["totalSubmissions"] == 6, ans["page"]["totalSubmissions"]
            assert len(ans["submissions"]) == 5, len(ans["submissions"])

        # Test with wrong pagination values
        async with client_logged_in.get(f"{submissions_url}?page=-1&projectId={project_id}") as resp:
            assert resp.status == 400
        async with client_logged_in.get(f"{submissions_url}?per_page=0&projectId={project_id}") as resp:
            assert resp.status == 400
        async with client_logged_in.get(f"{submissions_url}?published=asdf&projectId={project_id}") as resp:
            assert resp.status == 400

        for submission in submissions[:6]:
            await delete_submission(client_logged_in, submission)

    async def test_getting_submissions_filtered_by_name(self, client_logged_in, project_id):
        """Check that /submissions returns submissions filtered by name.

        :param client_logged_in: HTTP client in which request call is made
        :param project_id: id of the project the submission belongs to
        """
        names = [" filter new ", "_filter_", "-filter-", "_extra-", "_2021special_"]
        submissions = []
        for name in names:
            submission_data = {
                "name": f"Test{name}name",
                "description": "Test filtering name",
                "projectId": project_id,
                "workflow": "FEGA",
            }
            submissions.append(await post_submission(client_logged_in, submission_data))

        async with client_logged_in.get(f"{submissions_url}?name=filter&projectId={project_id}") as resp:
            ans = await resp.json()
            assert resp.status == 200, f"HTTP Status code error {resp.status} {ans}"
            assert ans["page"]["totalSubmissions"] == 3, f'Shold be 3 returned {ans["page"]["totalSubmissions"]}'

        async with client_logged_in.get(f"{submissions_url}?name=extra&projectId={project_id}") as resp:
            ans = await resp.json()
            assert resp.status == 200, f"HTTP Status code error {resp.status} {ans}"
            assert ans["page"]["totalSubmissions"] == 1

        async with client_logged_in.get(f"{submissions_url}?name=2021 special&projectId={project_id}") as resp:
            assert resp.status == 200
            ans = await resp.json()
            assert ans["page"]["totalSubmissions"] == 0

        async with client_logged_in.get(f"{submissions_url}?name=new extra&projectId={project_id}") as resp:
            assert resp.status == 200
            ans = await resp.json()
            assert ans["page"]["totalSubmissions"] == 2

        for submission in submissions:
            await delete_submission(client_logged_in, submission)

    async def test_getting_submissions_filtered_by_date_created(self, client_logged_in, database, project_id):
        """Check that /submissions returns submissions filtered by date created.

        :param client_logged_in: HTTP client in which request call is made
        :param database: database client to perform db operations
        :param project_id: id of the project the submission belongs to
        """
        submissions = []
        format = "%Y-%m-%d %H:%M:%S"

        # Test dateCreated within a year
        # Create submissions with different dateCreated
        timestamps = [
            "2014-12-31 00:00:00",
            "2015-01-01 00:00:00",
            "2015-07-15 00:00:00",
            "2016-01-01 00:00:00",
        ]
        for stamp in timestamps:
            submission_data = {
                "name": f"Test date {stamp}",
                "description": "Test filtering date",
                "dateCreated": datetime.strptime(stamp, format).timestamp(),
                "projectId": project_id,
            }
            submissions.append(await create_submission(database, submission_data))

        async with client_logged_in.get(
            f"{submissions_url}?date_created_start=2015-01-01&date_created_end=2015-12-31&projectId={project_id}"
        ) as resp:
            ans = await resp.json()
            assert resp.status == 200, f"returned status {resp.status}, error {ans}"
            assert ans["page"]["totalSubmissions"] == 2, f'Shold be 2 returned {ans["page"]["totalSubmissions"]}'

        # Test dateCreated within a month
        # Create submissions with different dateCreated
        timestamps = [
            "2013-01-31 00:00:00",
            "2013-02-02 00:00:00",
            "2013-03-29 00:00:00",
            "2013-04-01 00:00:00",
        ]
        for stamp in timestamps:
            submission_data = {
                "name": f"Test date {stamp}",
                "description": "Test filtering date",
                "dateCreated": datetime.strptime(stamp, format).timestamp(),
                "projectId": project_id,
            }
            submissions.append(await create_submission(database, submission_data))

        async with client_logged_in.get(
            f"{submissions_url}?date_created_start=2013-02-01&date_created_end=2013-03-30&projectId={project_id}"
        ) as resp:
            ans = await resp.json()
            assert resp.status == 200, f"returned status {resp.status}, error {ans}"
            assert ans["page"]["totalSubmissions"] == 2, f'Shold be 2 returned {ans["page"]["totalSubmissions"]}'

        # Test dateCreated within a day
        # Create submissions with different dateCreated
        timestamps = [
            "2012-01-14 23:59:59",
            "2012-01-15 00:00:01",
            "2012-01-15 23:59:59",
            "2012-01-16 00:00:01",
        ]
        for stamp in timestamps:
            submission_data = {
                "name": f"Test date {stamp}",
                "description": "Test filtering date",
                "dateCreated": datetime.strptime(stamp, format).timestamp(),
                "projectId": project_id,
            }
            submissions.append(await create_submission(database, submission_data))

        async with client_logged_in.get(
            f"{submissions_url}?date_created_start=2012-01-15&date_created_end=2012-01-15&projectId={project_id}"
        ) as resp:
            ans = await resp.json()
            assert resp.status == 200, f"returned status {resp.status}, error {ans}"
            assert ans["page"]["totalSubmissions"] == 2, f'Shold be 2 returned {ans["page"]["totalSubmissions"]}'

        # Test parameters date_created_... and name together
        async with client_logged_in.get(
            f"{submissions_url}?"
            f"name=2013&"
            f"date_created_start=2012-01-01&"
            f"date_created_end=2016-12-31&"
            f"projectId={project_id}"
        ) as resp:
            ans = await resp.json()
            assert resp.status == 200, f"returned status {resp.status}, error {ans}"
            assert ans["page"]["totalSubmissions"] == 4, f'Shold be 4 returned {ans["page"]["totalSubmissions"]}'

        for submission in submissions:
            await delete_submission(client_logged_in, submission)

    async def test_getting_submissions_filtered_by_date_modified(self, client_logged_in, database, project_id):
        """Check that /submissions returns submissions filtered by date modified.

        :param client_logged_in: HTTP client in which request call is made
        :param database: database client
        :param project_id: id of the project the submission belongs to
        """
        submissions = []
        format = "%Y-%m-%d %H:%M:%S"

        # Test lastModified within a year
        # Create submissions with different lastModified
        timestamps = [
            "2014-12-31 00:00:00",
            "2015-01-01 00:00:00",
            "2015-07-15 00:00:00",
            "2016-01-01 00:00:00",
        ]
        for stamp in timestamps:
            submission_data = {
                "name": f"Test date {stamp}",
                "description": "Test filtering date",
                "lastModified": datetime.strptime(stamp, format).timestamp(),
                "projectId": project_id,
            }
            submissions.append(await create_submission(database, submission_data))

        async with client_logged_in.get(
            f"{submissions_url}?date_modified_start=2015-01-01&date_modified_end=2015-12-31&projectId={project_id}"
        ) as resp:
            ans = await resp.json()
            assert resp.status == 200, f"returned status {resp.status}, error {ans}"
            assert ans["page"]["totalSubmissions"] == 2, f'Shold be 2 returned {ans["page"]["totalSubmissions"]}'

        # Test lastModified within a month
        # Create submissions with different lastModified
        timestamps = [
            "2013-01-31 00:00:00",
            "2013-02-02 00:00:00",
            "2013-03-29 00:00:00",
            "2013-04-01 00:00:00",
        ]
        for stamp in timestamps:
            submission_data = {
                "name": f"Test date {stamp}",
                "description": "Test filtering date",
                "lastModified": datetime.strptime(stamp, format).timestamp(),
                "projectId": project_id,
            }
            submissions.append(await create_submission(database, submission_data))

        async with client_logged_in.get(
            f"{submissions_url}?date_modified_start=2013-02-01&date_modified_end=2013-03-30&projectId={project_id}"
        ) as resp:
            ans = await resp.json()
            assert resp.status == 200, f"returned status {resp.status}, error {ans}"
            assert ans["page"]["totalSubmissions"] == 2, f'Shold be 2 returned {ans["page"]["totalSubmissions"]}'

        # Test lastModified within a day
        # Create submissions with different lastModified
        timestamps = [
            "2012-01-14 23:59:59",
            "2012-01-15 00:00:01",
            "2012-01-15 23:59:59",
            "2012-01-16 00:00:01",
        ]
        for stamp in timestamps:
            submission_data = {
                "name": f"Test date {stamp}",
                "description": "Test filtering date",
                "lastModified": datetime.strptime(stamp, format).timestamp(),
                "projectId": project_id,
            }
            submissions.append(await create_submission(database, submission_data))

        async with client_logged_in.get(
            f"{submissions_url}?date_modified_start=2012-01-15&date_modified_end=2012-01-15&projectId={project_id}"
        ) as resp:
            ans = await resp.json()
            assert resp.status == 200, f"returned status {resp.status}, error {ans}"
            assert ans["page"]["totalSubmissions"] == 2, f'Shold be 2 returned {ans["page"]["totalSubmissions"]}'

        # Test parameters date_created_... and name together
        async with client_logged_in.get(
            f"{submissions_url}?name=2013&date_modified_start=2012-01-01&"
            f"date_modified_end=2016-12-31&projectId={project_id}"
        ) as resp:
            ans = await resp.json()
            assert resp.status == 200, f"returned status {resp.status}, error {ans}"
            assert ans["page"]["totalSubmissions"] == 4, f'Shold be 4 returned {ans["page"]["totalSubmissions"]}'

        for submission in submissions:
            await delete_submission(client_logged_in, submission)


class TestSubmissionDataIngestion:
    """Testing data ingestion when the metadata submission with files is ready."""

    async def test_file_ingestion_works(self, client_logged_in, database, project_id, admin_token):
        """Test that files are ingested successfully and their status becomes 'ready'.

        :param client_logged_in: HTTP client in which request call is made
        :param database: database client to perform db operations
        :param project_id: id of the project the submission belongs to
        :param admin_token: a JWT with admin credentials
        """
        # Create new submission and check its creation succeeded
        submission_data = {
            "name": "Test submission",
            "description": "Mock a submission for testing file ingestion",
            "projectId": project_id,
            "workflow": "Bigpicture",
        }

        submission_id = await post_submission(client_logged_in, submission_data)
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug("Checking that submission %s was created", submission_id)
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        dataset_id, _ = await post_object(client_logged_in, "bpdataset", submission_id, "dataset.xml")

        await setup_files_for_ingestion(client_logged_in, dataset_id, submission_id, project_id, admin_token)

        db_submission = await database["submission"].find_one({"submissionId": submission_id})
        files_for_ingestion = []
        for db_submission_file in db_submission["files"]:
            # Assert the file status in submission is "added"
            assert db_submission_file["status"] == "added"
            db_file = await database["file"].find_one(
                {"accessionId": db_submission_file["accessionId"], "projectId": project_id}
            )
            files_for_ingestion.append({"accessionId": db_file["accessionId"], "path": db_file["path"]})

        # Start file ingestion
        await post_data_ingestion(client_logged_in, submission_id, admin_token)

        # Assert the file status in submission is changed to "ready"
        db_submission = await database["submission"].find_one({"submissionId": submission_id})
        for db_submission_file in db_submission["files"]:
            assert db_submission_file["status"] == "ready"

        async with aiohttp.ClientSession(headers={"Authorization": "Bearer " + admin_token}) as admin_client:
            # Assert the file accession IDs in archive are correct
            user_data = await get_user_data(client_logged_in)
            await check_file_accession_ids(admin_client, files_for_ingestion, user_data["externalId"])

            # Assert the dataset has been created correctly
            await check_dataset_accession_ids(admin_client, files_for_ingestion, dataset_id)
