"""Base operator class shared by operators."""

from abc import ABC

from motor.motor_asyncio import AsyncIOMotorClient

from ...conf.conf import mongo_database
from ...database.db_service import DBService


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
