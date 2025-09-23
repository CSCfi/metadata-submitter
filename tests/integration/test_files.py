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
        assert response.status == 400
        resp = await response.json()
        assert resp["detail"] == "No buckets found."

        await s3_manager.add_bucket("bucket1")
        await s3_manager.add_bucket("bucket2")
        response = await client_logged_in.get(f"{files_url}/{project_id}/buckets")
        assert response.status == 200
        buckets = await response.json()
        assert isinstance(buckets, list)
        assert set(buckets) == {"bucket1", "bucket2"}

        await s3_manager.add_bucket("bucket3")
        response = await client_logged_in.get(f"{files_url}/{project_id}/buckets")
        assert response.status == 200
        buckets = await response.json()
        assert "bucket3" in buckets

    async def test_list_files_in_bucket(self, client_logged_in, project_id, s3_manager):
        """Test listing files in a specific bucket."""
        bucket_name = "bucket1"
        response = await client_logged_in.get(f"{files_url}/{project_id}/buckets/{bucket_name}/files")
        assert response.status == 400
        resp = await response.json()
        assert resp["detail"] == "The specified bucket does not exist."

        await s3_manager.add_bucket(bucket_name)
        await s3_manager.add_file_to_bucket(bucket_name, "file1.txt")
        await s3_manager.add_file_to_bucket(bucket_name, "file2.txt")
        response = await client_logged_in.get(f"{files_url}/{project_id}/buckets/{bucket_name}/files")
        assert response.status == 200
        files = await response.json()
        assert isinstance(files, list)
        assert files[0]["path"] == f"S3://{bucket_name}/file1.txt"
        assert files[0]["bytes"] == 100
        assert files[1]["path"] == f"S3://{bucket_name}/file2.txt"
