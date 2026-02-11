"""Files API handler."""

from typing import Annotated

from fastapi import HTTPException, Path, Query, Request, Response, status

from ...api.dependencies import UserDependency
from ...helpers.logger import LOG
from ..services.file import FileProviderService
from .restapi import RESTAPIHandler

BucketNamePathParam = Annotated[str, Path(description="The bucket name")]
ProjectIdQueryParam = Annotated[str, Query(alias="projectId", description="The project ID")]


class FilesAPIHandler(RESTAPIHandler):
    """Files API handler."""

    async def get_project_buckets(
        self,
        request: Request,
        user: UserDependency,
        project_id: ProjectIdQueryParam,
    ) -> list[str]:
        """List all buckets in a specific project."""

        project_service = self._services.project
        file_service = self._services.file_provider
        keystone_service = self._handlers.keystone

        # Check that user is affiliated with the project.
        user_id = user.user_id
        await project_service.verify_user_project(user_id, project_id)

        # Get temporary user specific project scoped token.
        access_token = request.cookies.get("pouta_access_token")
        project_entry = await keystone_service.get_project_entry(project_id, access_token)
        credentials = await keystone_service.get_ec2_for_project(project_entry)

        # List all buckets in the requested project.
        buckets = await file_service.list_buckets(credentials)
        LOG.info("Retrieved %d buckets available for project %s.", len(buckets), project_id)

        # Delete temporary EC2 credentials after use
        await keystone_service.delete_ec2_from_project(project_entry, credentials)
        return buckets

    async def get_files_in_bucket(
        self,
        user: UserDependency,
        bucket: BucketNamePathParam,
        project_id: ProjectIdQueryParam,
    ) -> FileProviderService.Files:
        """List all files in a specific bucket."""

        project_service = self._services.project
        file_service = self._services.file_provider

        # Check that user is affiliated with the project.
        user_id = user.user_id
        await project_service.verify_user_project(user_id, project_id)

        files = await file_service.list_files_in_bucket(bucket)
        LOG.info("Retrieved %d files in bucket %s.", len(files.root), bucket)
        return files

    async def grant_access_to_bucket(
        self,
        request: Request,
        user: UserDependency,
        bucket: BucketNamePathParam,
        project_id: ProjectIdQueryParam,
    ) -> Response:
        """Grant this service access to a specific bucket."""

        project_service = self._services.project
        file_provider_service = self._services.file_provider
        keystone_handler = self._handlers.keystone

        # Check that user is affiliated with the project.
        user_id = user.user_id
        await project_service.verify_user_project(user_id, project_id)

        # Get temporary user specific project scoped token.
        access_token = request.cookies.get("pouta_access_token")
        project_entry = await keystone_handler.get_project_entry(project_id, access_token)
        credentials = await keystone_handler.get_ec2_for_project(project_entry)

        # Grant access to the bucket.
        await file_provider_service.update_bucket_policy(bucket, credentials)
        LOG.info("Granted access to bucket %s in project %s.", bucket, project_id)

        # Delete temporary EC2 credentials after use
        await keystone_handler.delete_ec2_from_project(project_entry, credentials)
        return Response(status_code=status.HTTP_200_OK)

    async def check_bucket_access(
        self,
        request: Request,
        user: UserDependency,
        bucket: BucketNamePathParam,
        project_id: ProjectIdQueryParam,
    ) -> Response:
        """Check if a specific bucket can be accessed by this service."""

        project_service = self._services.project
        file_provider_service = self._services.file_provider

        # Check that user is affiliated with the project.
        user_id = user.user_id
        await project_service.verify_user_project(user_id, project_id)

        # Check that the bucket has been assigned the correct policy.
        has_access = await file_provider_service.verify_bucket_policy(bucket)
        if not has_access:
            detail = f"Bucket {bucket} is not accessible in project {project_id}."
            LOG.error(detail)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=request)

        LOG.info("Bucket policy for bucket %s in project %s exists.", bucket, project_id)
        return Response(status_code=status.HTTP_200_OK)
