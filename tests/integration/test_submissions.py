"""Test operations with submissions."""
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime

from tests.integration.conf import (
    datacite_url,
    drafts_url,
    objects_url,
    submit_url,
    testfiles_root,
)
from tests.integration.helpers import (
    create_multi_file_request_data,
    create_request_json_data,
    create_submission,
    delete_object,
    delete_submission,
    delete_submission_publish,
    get_draft,
    get_object,
    post_draft,
    post_object,
    post_object_json,
    post_submission,
    publish_submission,
    put_submission_dac,
    put_submission_doi,
    submissions_url,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestSubmissions:
    """Test querying submissions and their objects."""

    async def test_get_submissions(self, client_logged_in, submission_id: str, project_id: str):
        """Test submissions REST API GET .

        :param client_logged_in: HTTP client in which request call is made
        :param submission_id: id of the submission used to group submission objects
        :param project_id: id of the project the submission belongs to
        """
        async with client_logged_in.get(f"{submissions_url}?projectId={project_id}") as resp:
            LOG.debug(f"Reading submission {submission_id}")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            response = await resp.json()
            LOG.error(response)
            assert len(response["submissions"]) == 1, len(response["submissions"])
            assert response["page"] == {
                "page": 1,
                "size": 5,
                "totalPages": 1,
                "totalSubmissions": 1,
            }
            assert response["submissions"][0]["submissionId"] == submission_id

    async def test_get_submissions_objects(self, client_logged_in, submission_id: str, project_id: str):
        """Test submissions REST API GET with objects.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_id: id of the submission used to group submission objects
        :param project_id: id of the project the submission belongs to
        """
        accession_id = await post_object_json(client_logged_in, "study", submission_id, "SRP000539.json")
        async with client_logged_in.get(f"{submissions_url}?projectId={project_id}") as resp:
            LOG.debug(f"Reading submission {submission_id}")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            response = await resp.json()
            assert len(response["submissions"]) == 1
            assert response["submissions"][0]["metadataObjects"][0]["accessionId"] == accession_id
            assert "tags" in response["submissions"][0]["metadataObjects"][0]
            assert response["submissions"][0]["metadataObjects"][0]["tags"]["submissionType"] == "Form"

        await delete_object(client_logged_in, "study", accession_id)

    async def test_submissions_work(self, client_logged_in, submission_id):
        """Test actions in submission XML files.

        :param client_logged_in: HTTP client in which request call is made
        :param submission_id: id of the submission used to group submission objects
        """
        # Post original submission with two 'add' actions
        sub_files = [
            ("submission", "ERA521986_valid.xml"),
            ("study", "SRP000539.xml"),
            ("sample", "SRS001433.xml"),
        ]
        submission_data = await create_multi_file_request_data(sub_files)

        async with client_logged_in.post(
            f"{submit_url}", params={"submission": submission_id}, data=submission_data
        ) as resp:
            LOG.debug("Checking initial submission worked")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
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
            metax_id = res.get("metaxIdentifier", None)
            doi = res.get("doi", None)
            assert metax_id is not None
            assert doi is not None

        # check that objects are added to submission
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was patched")
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
        async with client_logged_in.post(f"{submit_url}", data=more_submission_data) as resp:
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
            assert res["metaxIdentifier"] == metax_id
            assert res["doi"] == doi

        # check that study is updated to submission
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was patched")
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
        }
        submission_id = await post_submission(client_logged_in, submission_data)
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was created")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Create draft from test XML file and patch the draft into the newly created submission
        draft_id = await post_draft(client_logged_in, "sample", submission_id, "SRS001433.xml")
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was patched")
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
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
            params={"submission": submission_id},
            data=draft_data,
        ) as resp:
            LOG.debug("Adding draft to actual objects")
            assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
            ans = await resp.json()
            assert ans["accessionId"] != draft_id, "draft id does not match expected"
            accession_id = ans["accessionId"]

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was patched")
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
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
        await put_submission_doi(client_logged_in, submission_id, doi_data_raw)

        # add a study and dataset for publishing a submission
        ds_1 = await post_object(client_logged_in, "dataset", submission_id, "dataset.xml")
        ds_1 = await get_object(client_logged_in, "dataset", ds_1[0])

        study = await post_object_json(client_logged_in, "study", submission_id, "SRP000539.json")
        study = await get_object(client_logged_in, "study", study)

        ds_2 = await post_object(client_logged_in, "dataset", submission_id, "dataset_put.xml")
        ds_2 = await get_object(client_logged_in, "dataset", ds_2[0])

        dac_data = await create_request_json_data("dac", "dac_rems.json")
        await put_submission_dac(client_logged_in, submission_id, dac_data)

        submission_id = await publish_submission(client_logged_in, submission_id)

        await get_draft(client_logged_in, "sample", draft_id, 404)  # checking the draft was deleted after publication

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was patched")
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
            assert res["published"] is True, "submission is not published, expected True"
            assert "datePublished" in res.keys()
            assert "extraInfo" in res.keys()
            assert res["drafts"] == [], "there are drafts in submission, expected empty"
            assert len(res["metadataObjects"]) == 4, "submission metadataObjects content mismatch"

        # check that datacite has references between datasets and study
        async with client_logged_in.get(f"{datacite_url}/{ds_1['doi']}") as datacite_resp:
            assert datacite_resp.status == 200, f"HTTP Status code error, got {datacite_resp.status}"
            datacite_res = await datacite_resp.json()
            ds_1 = datacite_res
        async with client_logged_in.get(f"{datacite_url}/{ds_2['doi']}") as datacite_resp:
            assert datacite_resp.status == 200, f"HTTP Status code error, got {datacite_resp.status}"
            datacite_res = await datacite_resp.json()
            ds_2 = datacite_res
        async with client_logged_in.get(f"{datacite_url}/{study['doi']}") as datacite_resp:
            assert datacite_resp.status == 200, f"HTTP Status code error, got {datacite_resp.status}"
            datacite_res = await datacite_resp.json()
            study = datacite_res
        assert ds_1["data"]["attributes"]["relatedIdentifiers"][0]["relatedIdentifier"] == study["id"]
        assert ds_2["data"]["attributes"]["relatedIdentifiers"][0]["relatedIdentifier"] == study["id"]
        for id in study["data"]["attributes"]["relatedIdentifiers"]:
            assert id["relatedIdentifier"] in {ds_1["id"], ds_2["id"]}

        # Delete submission
        await delete_submission_publish(client_logged_in, submission_id)

        async with client_logged_in.get(f"{drafts_url}/sample/{draft_id}") as resp:
            LOG.debug(f"Checking that JSON object {accession_id} was deleted")
            assert resp.status == 404, f"HTTP Status code error, got {resp.status}"

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
        }
        submission_id = await post_submission(client_logged_in, submission_data)
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was created")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Create draft from test XML file and patch the draft into the newly created submission
        draft_id = await post_draft(client_logged_in, "sample", submission_id, "SRS001433.xml")
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was patched")
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
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
            f"{objects_url}/sample", params={"submission": submission_id}, data=draft
        ) as resp:
            LOG.debug("Adding draft to actual objects")
            assert resp.status == 201, f"HTTP Status code error, got {resp.status}"
            ans = await resp.json()
            assert ans["accessionId"] != draft_id, "draft id does not match expected"
            accession_id = ans["accessionId"]

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was patched")
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
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
        await delete_submission(client_logged_in, submission_id)
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was deleted")
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
        }
        submission_id = await post_submission(client_logged_in, submission_data)
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was created")
            assert resp.status == 200, f"HTTP Status code error, got {resp.status}"

        # Get correctly formatted DOI info and patch it into the new submission successfully
        doi_data_raw = await create_request_json_data("doi", "test_doi.json")
        doi_data = json.loads(doi_data_raw)
        await put_submission_doi(client_logged_in, submission_id, doi_data_raw)

        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was patched")
            res = await resp.json()
            assert res["submissionId"] == submission_id, "expected submission id does not match"
            assert res["name"] == submission_data["name"], "expected submission name does not match"
            assert res["description"] == submission_data["description"], "submission description content mismatch"
            assert res["published"] is False, "submission is published, expected False"
            assert res["doiInfo"] == doi_data, "submission doi does not match"

        # Test that an incomplete DOI object fails to patch into the submission
        put_bad_doi = {"identifier": {}}
        async with client_logged_in.put(f"{submissions_url}/{submission_id}/doi", data=json.dumps(put_bad_doi)) as resp:
            LOG.debug(f"Tried updating submission {submission_id}")
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            assert (
                res["detail"] == "Provided input does not seem correct for field: 'doiInfo'"
            ), "expected error mismatch"

        # Check the existing DOI info is not altered
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was not patched with bad DOI")
            res = await resp.json()
            assert res["doiInfo"] == doi_data, "submission doi does not match"

        # Test that extraInfo cannot be altered
        patch_add_bad_doi = [{"op": "add", "path": "/extraInfo", "value": {"publisher": "something"}}]
        async with client_logged_in.patch(
            f"{submissions_url}/{submission_id}", data=json.dumps(patch_add_bad_doi)
        ) as resp:
            LOG.debug(f"Tried updating submission {submission_id}")
            assert resp.status == 400, f"HTTP Status code error, got {resp.status}"
            res = await resp.json()
            detail = res["detail"]
            assert (
                detail == "Patch submission operation should be provided as a JSON object"
            ), f"error mismatch, got '{detail}'"

        # Delete submission
        await delete_submission(client_logged_in, submission_id)
        async with client_logged_in.get(f"{submissions_url}/{submission_id}") as resp:
            LOG.debug(f"Checking that submission {submission_id} was deleted")
            assert resp.status == 404, f"HTTP Status code error, got {resp.status}"


class TestSubmissionPagination:
    """Testing getting submissions, draft submissions and draft templates with pagination."""

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
            }
            submissions.append(await post_submission(client_logged_in, submission_data))

        for submission_id in submissions[6:9]:
            await post_object_json(client_logged_in, "study", submission_id, "SRP000539.json")
            doi_data_raw = await create_request_json_data("doi", "test_doi.json")
            await put_submission_doi(client_logged_in, submission_id, doi_data_raw)
            dac_data = await create_request_json_data("dac", "dac_rems.json")
            await put_submission_dac(client_logged_in, submission_id, dac_data)
            await publish_submission(client_logged_in, submission_id)

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
