"""Base operator class shared by operators."""
from abc import ABC
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorClient

from ...conf.conf import mongo_database
from ...database.db_service import DBService
from ...helpers.logger import LOG


class BaseOperator(ABC):
    """Base class for operators, implements shared functionality.

    Used with other operators than the object operators
    :param ABC: The abstract base class
    """

    def __init__(self, db_client: AsyncIOMotorClient) -> None:
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
