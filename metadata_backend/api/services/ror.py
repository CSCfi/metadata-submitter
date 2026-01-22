"""ROR service."""

from abc import ABC, abstractmethod

from pydantic_string_url import AnyUrl


class RorService(ABC):
    """ROR service."""

    @abstractmethod
    async def get_organisation(self, organisation: str) -> tuple[AnyUrl, str] | None:
        """
        Get the ROR organisation if it exists and return the ROR identifier and preferred name.

        :param organisation: the organisation name
        :return: The ROR identifier and preferred name, or None.
        """
