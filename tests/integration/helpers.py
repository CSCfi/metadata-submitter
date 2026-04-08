"""Helper functions for the integration tests."""

import hashlib
import json
import logging
import os
import time
from base64 import urlsafe_b64encode
from typing import Any

import aioboto3
import aiohttp

from metadata_backend.api.models.models import Objects, Registration
from metadata_backend.api.models.submission import Submission
from metadata_backend.conf.deployment import deployment_config

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


async def patch_submission(sess: aiohttp.ClientSession, submission_id: str, submission_dict: dict[str, Any]):
    """Change submission document using /submissions endpoint."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    async with sess.patch(f"{api_prefix_v1}/submissions/{submission_id}", json=submission_dict) as resp:
        assert resp.status == 200
        ans_patch = await resp.json()
        assert ans_patch["submissionId"] == submission_id, "submission ID error"
        return ans_patch["submissionId"]


async def patch_submission_bucket(sess: aiohttp.ClientSession, submission_id: str, bucket: str):
    """Change submission bucket using /submissions endpoint."""
    await patch_submission(sess, submission_id, {"bucket": bucket})


async def publish_submission(sess: aiohttp.ClientSession, submission_id: str, *, no_files: bool = True):
    """Publish submission."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    async with sess.patch(f"{api_prefix_v1}/publish/{submission_id}?no_files={str(no_files).lower()}") as resp:
        result = await resp.json()
        assert resp.status == 200, f"Publish failed with status {resp.status}: {result}"
        assert result["submissionId"] == submission_id


async def get_submission(sess: aiohttp.ClientSession, submission_id: str) -> Submission:
    """Get submission document with the given submission id."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    async with sess.get(f"{api_prefix_v1}/submissions/{submission_id}") as resp:
        data = await resp.json()
        assert resp.status == 200, f"Expected status 200, got {resp.status}: {data}"
        return Submission.model_validate(data)


async def get_objects(sess: aiohttp.ClientSession, submission_id: str) -> Objects:
    """Get submission objects with the given submission id."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    async with sess.get(f"{api_prefix_v1}/submissions/{submission_id}/objects") as resp:
        data = await resp.json()
        assert resp.status == 200, f"Expected status 200, got {resp.status}: {data}"
        return Objects.model_validate(data)


async def get_files(sess: aiohttp.ClientSession, submission_id: str) -> list[dict[str, Any]]:
    """Get submission files with the given submission id."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    async with sess.get(f"{api_prefix_v1}/submissions/{submission_id}/files") as resp:
        data = await resp.json()
        assert resp.status == 200, f"Expected status 200, got {resp.status}: {data}"
        return data


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

    api_prefix_v1 = deployment_config().API_PREFIX_V1
    params = {
        "objectType": object_type,
        "schemaType": schema_type,
        "objectId": object_id,
        "objectName": object_name,
    }
    params = {k: v for k, v in params.items() if v is not None}

    async with sess.get(f"{api_prefix_v1}/submissions/{submission_id}/objects/docs", params=params) as resp:
        data = await resp.text()
        assert resp.status == 200
        return data


async def get_registrations(sess: aiohttp.ClientSession, submission_id: str) -> Registration:
    """Get registrations with the given submission id."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    async with sess.get(f"{api_prefix_v1}/submissions/{submission_id}/registrations") as resp:
        data = await resp.json()
        assert resp.status == 200, f"Expected status 200, got {resp.status}: {data}"
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


async def add_file_to_bucket(bucket_name, object_key, access_key, secret_key, endpoint_url, region, session_token=None):
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
        aws_session_token=session_token,
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


async def seed_mock_admin_files(client: aiohttp.ClientSession, user_id: str, submission_id: str) -> None:
    """Add existing submission data file paths to mock Admin inbox state for integration tests."""
    admin_url = "http://mockadmin:8004" if os.getenv("CICD") == "true" else "http://localhost:8004"
    admin_token = os.getenv("ADMIN_TOKEN", "")
    if admin_token:
        auth_value = f"Bearer {admin_token}"
    else:
        header = (
            urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8")).decode("utf-8").rstrip("=")
        )
        payload = (
            urlsafe_b64encode(json.dumps({"sub": user_id, "exp": int(time.time()) + 3600}).encode("utf-8"))
            .decode("utf-8")
            .rstrip("=")
        )
        auth_value = f"Bearer {header}.{payload}.signature"

    headers = {"Authorization": auth_value}

    api_prefix_v1 = deployment_config().API_PREFIX_V1
    async with client.get(f"{api_prefix_v1}/submissions/{submission_id}/files") as resp:
        assert resp.status == 200
        submission_files = await resp.json()

    inbox_paths = {
        file["path"] for file in submission_files if isinstance(file, dict) and isinstance(file.get("path"), str)
    }

    async with aiohttp.ClientSession(base_url=admin_url, headers=headers) as admin_client:
        for inbox_path in sorted(inbox_paths):
            payload = {"user": user_id, "filepath": inbox_path}
            async with admin_client.post("/file/create", json=payload) as resp:
                assert resp.status == 201


async def get_user_id(sess: aiohttp.ClientSession):
    """Get user ID from /users/me endpoint."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    async with sess.get(f"{api_prefix_v1}/users/") as resp:
        data = await resp.json()
        assert resp.status == 200, f"Expected status 200, got {resp.status}: {data}"
        return data["user_id"]
