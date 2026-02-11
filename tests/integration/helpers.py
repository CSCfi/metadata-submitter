"""Helper functions for the integration tests."""

import hashlib
import logging
import os
from typing import Any

import aioboto3
import aiohttp

from metadata_backend.api.models.models import Objects, Registration
from metadata_backend.api.models.submission import Submission

from .conf import (
    publish_url,
    submissions_url,
)

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


async def patch_submission(sess: aiohttp.ClientSession, submission_id: str, submission_dict: dict[str, Any]):
    """Change submission document using /submissions endpoint."""
    async with sess.patch(f"{submissions_url}/{submission_id}", json=submission_dict) as resp:
        assert resp.status == 200
        ans_patch = await resp.json()
        assert ans_patch["submissionId"] == submission_id, "submission ID error"
        return ans_patch["submissionId"]


async def patch_submission_bucket(sess: aiohttp.ClientSession, submission_id: str, bucket: str):
    """Change submission bucket using /submissions endpoint."""
    await patch_submission(sess, submission_id, {"bucket": bucket})


async def publish_submission(sess: aiohttp.ClientSession, submission_id: str, *, no_files: bool = True):
    """Publish submission."""
    async with sess.patch(f"{publish_url}/{submission_id}?no_files={str(no_files).lower()}") as resp:
        result = await resp.json()
        assert resp.status == 200
        assert result["submissionId"] == submission_id


async def get_submission(sess: aiohttp.ClientSession, submission_id: str) -> Submission:
    """Get submission document with the given submission id."""

    async with sess.get(f"{submissions_url}/{submission_id}") as resp:
        data = await resp.json()
        assert resp.status == 200
        return Submission.model_validate(data)


async def get_objects(sess: aiohttp.ClientSession, submission_id: str) -> Objects:
    """Get submission objects with the given submission id."""

    async with sess.get(f"{submissions_url}/{submission_id}/objects") as resp:
        data = await resp.json()
        assert resp.status == 200
        return Objects.model_validate(data)


async def get_docs(
    sess: aiohttp.ClientSession,
    submission_id: str,
    *,
    object_type: str | None = None,
    schema_type: str | None = None,
    object_id: str | None = None,
    object_name: str | None = None,
) -> str:
    """Get submission documents with the given submission id."""

    params = {
        "objectType": object_type,
        "schemaType": schema_type,
        "objectId": object_id,
        "objectName": object_name,
    }
    params = {k: v for k, v in params.items() if v is not None}

    async with sess.get(f"{submissions_url}/{submission_id}/objects/docs", params=params) as resp:
        data = await resp.text()
        assert resp.status == 200
        return data


async def get_registrations(sess: aiohttp.ClientSession, submission_id: str) -> Registration:
    """Get registrations with the given submission id."""

    async with sess.get(f"{submissions_url}/{submission_id}/registrations") as resp:
        data = await resp.json()
        assert resp.status == 200
        return Registration.model_validate(data)


async def add_bucket(bucket_name, access_key, secret_key, endpoint_url, region):
    """Add a new S3 bucket using provided credentials.

    :param bucket_name: name of the bucket
    :param access_key: S3 access key ID
    :param secret_key: S3 secret access key
    :param endpoint_url: S3 endpoint URL
    :param region: S3 region
    """
    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    ) as s3:
        await s3.create_bucket(Bucket=bucket_name)


async def add_file_to_bucket(bucket_name, object_key, access_key, secret_key, endpoint_url, region):
    """Add a new object to S3 bucket using provided credentials.

    :param bucket_name: name of the bucket
    :param object_key: key for the object to be added
    :param access_key: S3 access key ID
    :param secret_key: S3 secret access key
    :param endpoint_url: S3 endpoint URL
    :param region: S3 region
    """
    random_bytes = os.urandom(100)  # 100 bytes of random data
    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    ) as s3:
        await s3.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=random_bytes,
            ChecksumSHA256=hashlib.sha256(random_bytes).hexdigest(),
        )


async def delete_bucket(bucket_name, access_key, secret_key, endpoint_url, region):
    """Delete a S3 bucket and its contentsusing provided credentials.

    :param bucket_name: name of the bucket
    :param access_key: S3 access key ID
    :param secret_key: S3 secret access key
    :param endpoint_url: S3 endpoint URL
    :param region: S3 region
    """
    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        use_ssl=False,
    ) as s3:
        # First, delete all objects in the bucket
        try:
            objects = await s3.list_objects_v2(Bucket=bucket_name)
            if "Contents" in objects:
                for obj in objects["Contents"]:
                    await s3.delete_object(Bucket=bucket_name, Key=obj["Key"])
        except Exception:
            pass  # Bucket might be empty or not exist

        # Then delete the bucket
        await s3.delete_bucket(Bucket=bucket_name)
