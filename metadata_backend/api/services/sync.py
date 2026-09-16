"""Sync services."""

from abc import ABC, abstractmethod


class SyncMetadataProvider(ABC):
    """How a deployment packages the metadata objects of a submission for syncing.

    Aggregating metadata objects into one archive is defined by a a workflow.
    """

    @abstractmethod
    async def get_metadata_archive(self, submission_id: str) -> bytes:
        """
        Get the metadata objects of one submission as a zip archive.

        :param submission_id: The submission id.
        :return: The zip archive of the metadata objects.
        """
