"""Base operator class shared by operators."""

from abc import ABC
from secrets import choice
from string import ascii_lowercase, digits
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorClient

from ...conf.conf import BP_CENTER_ID, BP_SCHEMA_TYPES, mongo_database
from ...database.db_service import DBService
from ...helpers.logger import LOG


class BaseOperator(ABC):
    """Base class for operators, implements shared functionality.

    Used with other operators than the object operators
    :param ABC: The abstract base class
    """

    def __init__(self, db_client: AsyncIOMotorClient) -> None:  # type: ignore
        """Init db_service.

        :param db_client: Motor client used for database connections. Should be
        running on same loop with aiohttp, so needs to be passed from aiohttp
        Application.
        """
        self.db_service = DBService(mongo_database, db_client)

    def _generate_accession_id(self) -> str:
        """Generate random accession id.

        :returns: accession id as str
        """
        sequence = uuid4().hex
        LOG.debug("Generated project ID.")
        return sequence

    def _generate_bp_accession_id(self, schema_type: str) -> str:
        """Generate accession id for Bigpicture metadata objects.

        :param schema_type: schema type of Bigpicture object to have accession id generated
        :returns: BP accession id as str
        """
        allowed_chars = "".join(c for c in ascii_lowercase + digits if c not in "ilo01")
        sequence = "".join(choice(allowed_chars) for _ in range(12))

        if schema_type not in BP_SCHEMA_TYPES:
            reason = "Provided invalid Bigpicture schema type."
            LOG.error(reason)
            raise ValueError(reason)

        bp_id = f"{BP_CENTER_ID}-{schema_type[2:]}-{sequence[0:6]}-{sequence[6:12]}"
        LOG.debug("Generated Bigpicture accession ID.")
        return bp_id
