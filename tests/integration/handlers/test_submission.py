"""Test operations with submissions."""

import logging
import uuid

from metadata_backend.api.json import to_json
from tests.integration.helpers import (
    get_docs,
    get_objects,
    get_submission,
    patch_submission_bucket,
    submissions_url,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


async def test_sd_submission(sd_client, sd_submission, sd_submission_update):
    """Test post, get and delete SD submission using /submissions endpoint."""

    # Create submission.
    submission = await sd_submission()
    submission_id = submission.submissionId

    # Create another submission with the same name fails.
    async with sd_client.post(f"{submissions_url}", data=to_json(submission)) as resp:
        res = await resp.json()
        assert resp.status == 400
        assert (
            res["detail"]
            == f"Submission with name '{submission.name}' already exists in project {submission.projectId}"
        )

    # Get submission.
    saved_submission = await get_submission(sd_client, submission_id)
    assert saved_submission.submissionId == submission_id
    assert saved_submission.name == submission.name
    assert saved_submission.description == submission.description
    assert not saved_submission.published

    # Update submission.
    updated_title = f"name_{uuid.uuid4()}"
    updated_submission = await sd_submission_update(submission.submissionId, {"title": updated_title})
    assert updated_submission.title == updated_title

    # Delete submission.
    async with sd_client.delete(f"{submissions_url}/{submission_id}") as resp:
        assert resp.status == 204

    # Get submission.
    async with sd_client.get(f"{submissions_url}/{submission_id}") as resp:
        assert resp.status == 404


async def test_sd_bucket(sd_client, sd_submission):
    """Test that a bucket name can be linked to a submission."""

    submission = await sd_submission()
    submission_id = submission.submissionId

    async with sd_client.get(f"{submissions_url}/{submission_id}") as resp:
        assert resp.status == 200

    submission = await get_submission(sd_client, submission_id)
    assert submission.bucket is None

    bucket = "test"
    await patch_submission_bucket(sd_client, submission_id, bucket)
    submission = await get_submission(sd_client, submission_id)
    assert submission.bucket == bucket


async def test_bp_objects_and_docs(nbis_client, sd_submission, project_id, bp_submission):
    """Test get BigPicture objects and XML docs for NBIS deployment."""

    # Create submission.
    submission = await bp_submission()
    submission_id = submission.submissionId

    # Get objects.
    objects = (await get_objects(nbis_client, submission_id)).root

    def assert_exactly_one(name: str, object_type: str) -> None:
        assert sum(obj.name == name and obj.objectType == object_type for obj in objects) == 1, (
            f"Expected exactly one {object_type!r} with name={name!r}"
        )

    assert_exactly_one(name="1", object_type="dataset")
    assert_exactly_one(name="1", object_type="policy")
    assert_exactly_one(name="1", object_type="image")
    assert_exactly_one(name="2", object_type="image")
    assert_exactly_one(name="1", object_type="annotation")
    assert_exactly_one(name="1", object_type="observation")
    assert_exactly_one(name="1", object_type="observer")
    assert_exactly_one(name="1", object_type="biologicalbeing")
    assert_exactly_one(name="1", object_type="case")
    assert_exactly_one(name="1", object_type="specimen")
    assert_exactly_one(name="1", object_type="block")
    assert_exactly_one(name="1", object_type="slide")
    assert_exactly_one(name="1", object_type="staining")
    assert_exactly_one(name="1", object_type="landingpage")
    assert_exactly_one(name="1", object_type="rems")
    assert_exactly_one(name="1", object_type="organisation")

    def get_exactly_one(name: str, object_type: str):
        matches = [obj for obj in objects if obj.name == name and obj.objectType == object_type]
        assert len(matches) == 1, f"Expected exactly one {object_type!r} with name={name!r}, found {len(matches)}"
        return matches[0]

    dataset = get_exactly_one(name="1", object_type="dataset")
    image = get_exactly_one(name="1", object_type="image")
    annotation = get_exactly_one(name="1", object_type="annotation")
    observation = get_exactly_one(name="1", object_type="observation")

    expected_xml = f"""<?xml version='1.0' encoding='UTF-8'?>
<DATASET_SET>
  <DATASET alias="1" accession="{dataset.objectId}">
    <TITLE>test_title</TITLE>
    <SHORT_NAME>test_short_name</SHORT_NAME>
    <DESCRIPTION>test_description</DESCRIPTION>
    <VERSION>1</VERSION>
    <METADATA_STANDARD>2.0.0</METADATA_STANDARD>
    <IMAGE_REF alias="1" accession="{image.objectId}"/>
    <ANNOTATION_REF alias="1" accession="{annotation.objectId}"/>
    <OBSERVATION_REF alias="1" accession="{observation.objectId}"/>
    <ATTRIBUTES>
      <STRING_ATTRIBUTE>
        <TAG>test</TAG>
        <VALUE>test approval</VALUE>
      </STRING_ATTRIBUTE>
    </ATTRIBUTES>
  </DATASET>
</DATASET_SET>
"""

    # Get dataset document by object type and name.
    xml = await get_docs(nbis_client, submission_id, object_type="dataset", object_name=dataset.name)
    assert xml == expected_xml

    # Get dataset document by object type and id.
    xml = await get_docs(nbis_client, submission_id, object_type="dataset", object_id=dataset.objectId)
    assert xml == expected_xml

    # Get dataset document by schema type and name.
    xml = await get_docs(nbis_client, submission_id, schema_type="dataset", object_name=dataset.name)
    assert xml == expected_xml

    # Get dataset document by schema type and id.
    xml = await get_docs(nbis_client, submission_id, schema_type="dataset", object_id=dataset.objectId)
    assert xml == expected_xml
