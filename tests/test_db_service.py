"""Test db_services."""
import copy
from mongomock import MongoClient
from aiounittest import AsyncTestCase, futurized
from mock import MagicMock, Mock
from pymongo.results import InsertOneResult

from metadata_backend.database.db_service import DBService


class DatabaseTestCase(AsyncTestCase):
    """Test different database operations."""

    def setUp(self):
        """Setup test service with mock client.

        Monkey patches MagicMock to work with async / await, then adds
        return values for used pymongo methods.

        Tests should be using collection "test" inside database "test" to
        ensure they work with correct mocked values.
        """
        async def async_patch():
            pass
        MagicMock.__await__ = lambda x: async_patch().__await__()

        self.client = MagicMock()
        self.database = MagicMock()
        self.collection = MagicMock()
        self.client.__getitem__.return_value = self.database
        self.database.__getitem__.return_value = self.collection
        self.test_service = DBService("test", self.client)

    def test_db_services_share_mongodb_client(self):
        """Test client is shared across different db_service_objects."""
        foo = DBService("foo", self.client)
        bar = DBService("bar", self.client)
        assert foo.db_client is bar.db_client

    async def test_create_works(self):
        """Test that basic crud stuff works as expected."""
        self.collection.insert_one.return_value = futurized(
            InsertOneResult("EGA123456", True)
        )
        data = {"accessionId": "EGA123456",
                'identifiers': ["foo", "bar"]
                }
        success = await self.test_service.create("test", data)
        assert success
