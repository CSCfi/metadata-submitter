"""ROR service."""

from abc import ABC, abstractmethod


class RorService(ABC):
    """ROR service."""

    @abstractmethod
    async def is_ror_organisation(self, organisation: str) -> str | None:
        """
        Check if the ROR organisation exists and return the preferred name or None.

        :param organisation: the organisation name
        :return: The preferred name or None
        """
