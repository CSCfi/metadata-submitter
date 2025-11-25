"""Test operations with files."""

import logging

from tests.integration.conf import files_url

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class TestFiles:
    """Test fetching files from S3 API."""

    async def test_list_buckets(self, client_logged_in, project_id, s3_manager):
        """Test listing buckets in a project."""
        response = await client_logged_in.get(f"{files_url}/{project_id}/buckets")
        assert response.status == 404
        resp = await response.json()
        assert resp["detail"] == "No buckets found."

        await s3_manager.add_bucket("bucket1")
        await s3_manager.add_bucket("bucket2")
        await s3_manager.set_bucket_policy("bucket1", project_id)
        await s3_manager.set_bucket_policy("bucket2", project_id)

        response = await client_logged_in.get(f"{files_url}/{project_id}/buckets")
        assert response.status == 200
        buckets = await response.json()
        assert isinstance(buckets, list)
        assert set(buckets) == {"bucket1", "bucket2"}

        await s3_manager.add_bucket("bucket3")
        await s3_manager.set_bucket_policy("bucket3", "some_other_project")
        response = await client_logged_in.get(f"{files_url}/{project_id}/buckets")
        assert response.status == 200
        buckets = await response.json()
        assert "bucket3" not in buckets

    async def test_list_files_in_bucket(self, client_logged_in, project_id, s3_manager):
        """Test listing files in a specific bucket."""
        bucket_name = "bucket1"
        response = await client_logged_in.get(f"{files_url}/{project_id}/buckets/{bucket_name}/files")
        assert response.status == 400
        resp = await response.json()
        assert resp["detail"] == f"Bucket {bucket_name} is not accessible in project {project_id}."

        await s3_manager.add_bucket(bucket_name)
        await s3_manager.add_file_to_bucket(bucket_name, "file1.txt")
        await s3_manager.add_file_to_bucket(bucket_name, "file2.txt")
        await s3_manager.set_bucket_policy(bucket_name, project_id)

        response = await client_logged_in.get(f"{files_url}/{project_id}/buckets/{bucket_name}/files")
        assert response.status == 200
        files = await response.json()
        LOG.debug(response.reason)
        assert isinstance(files, list)
        assert files[0]["path"] == f"S3://{bucket_name}/file1.txt"
        assert files[0]["bytes"] == 100
        assert files[1]["path"] == f"S3://{bucket_name}/file2.txt"

    async def test_grant_access_to_bucket(self, client_logged_in, project_id, s3_manager):
        """Test creating and reading bucket policies of a bucket in a project."""
        bucket_name = "bucket1"
        response = await client_logged_in.put(f"{files_url}/{project_id}/buckets/{bucket_name}")
        assert response.status == 400
        resp = await response.json()
        assert resp["detail"] == "The specified bucket does not exist"

        await s3_manager.add_bucket(bucket_name)
        response = await client_logged_in.head(f"{files_url}/{project_id}/buckets/{bucket_name}")
        assert response.status == 400

        response = await client_logged_in.put(f"{files_url}/{project_id}/buckets/{bucket_name}")
        assert response.status == 200
        response = await client_logged_in.head(f"{files_url}/{project_id}/buckets/{bucket_name}")
        assert response.status == 200

        # Granting again should be idempotent
        response = await client_logged_in.put(f"{files_url}/{project_id}/buckets/{bucket_name}")
        assert response.status == 200
        response = await client_logged_in.head(f"{files_url}/{project_id}/buckets/{bucket_name}")
        assert response.status == 200
