"""Test db_services."""
from aiounittest import AsyncTestCase, futurized
from unittest.mock import MagicMock, patch
from pymongo.results import InsertOneResult, UpdateResult, DeleteResult
from pymongo.errors import AutoReconnect, ConnectionFailure
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCursor

from metadata_backend.database.db_service import DBService


class DatabaseTestCase(AsyncTestCase):
    """Test different database operations."""

    def setUp(self):
        """Initialize test service with mock client.

        Monkey patches MagicMock to work with async / await, then sets up
        client->database->collection -structure pymongo uses.

        Monkey patching can probably be removed when upgrading requirements to
        python 3.8+ since Mock 4.0+ library has async version of MagicMock.
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
        self.id_stub = "EGA123456"
        self.data_stub = {"accessionId": self.id_stub,
                          "identifiers": ["foo", "bar"]
                          }

    def test_db_services_share_mongodb_client(self):
        """Test client is shared across different db_service_objects."""
        foo = DBService("foo", self.client)
        bar = DBService("bar", self.client)
        self.assertIs(foo.db_client, bar.db_client)

    async def test_create_inserts_data(self):
        """Test that create method works and returns success."""
        self.collection.insert_one.return_value = futurized(
            InsertOneResult(ObjectId('0123456789ab0123456789ab'), True)
        )
        success = await self.test_service.create("test", self.data_stub)
        self.collection.insert_one.assert_called_once_with(self.data_stub)
        self.assertTrue(success)

    async def test_create_reports_fail_correctly(self):
        """Test that failure is reported, when write not acknowledged."""
        self.collection.insert_one.return_value = futurized(
            InsertOneResult(None, False)
        )
        success = await self.test_service.create("test", self.data_stub)
        self.collection.insert_one.assert_called_once_with(self.data_stub)
        self.assertFalse(success)

    async def test_read_returns_data(self):
        """Test that read method works and returns data."""
        self.collection.find_one.return_value = futurized(self.data_stub)
        found_doc = await self.test_service.read("test", self.id_stub)
        self.assertEqual(found_doc, self.data_stub)
        self.collection.find_one.assert_called_once_with({"accessionId":
                                                          self.id_stub})

    async def test_update_updates_data(self):
        """Test that update method works and returns success."""
        self.collection.update_one.return_value = futurized(
            UpdateResult({}, True)
        )
        success = await self.test_service.update("test", self.id_stub,
                                                 self.data_stub)
        self.collection.update_one.assert_called_once_with({"accessionId":
                                                            self.id_stub},
                                                           {"$set":
                                                            self.data_stub})
        self.assertTrue(success)

    async def test_replace_replaces_data(self):
        """Test that replace method works and returns success."""
        self.collection.replace_one.return_value = futurized(
            UpdateResult({}, True)
        )
        success = await self.test_service.replace("test", self.id_stub,
                                                  self.data_stub)
        self.collection.replace_one.assert_called_once_with({"accessionId":
                                                            self.id_stub},
                                                            self.data_stub)
        self.assertTrue(success)

    async def test_delete_deletes_data(self):
        """Test that delete method works and returns success."""
        self.collection.delete_one.return_value = futurized(
            DeleteResult({}, True)
        )
        success = await self.test_service.delete("test", self.id_stub)
        self.collection.delete_one.assert_called_once_with({"accessionId":
                                                           self.id_stub})
        self.assertTrue(success)

    def test_query_executes_find(self):
        """Test that find is executed, so cursor is returned."""
        self.collection.find.return_value = AsyncIOMotorCursor(None, None)
        cursor = self.test_service.query("test", {})
        self.assertEqual(type(cursor), AsyncIOMotorCursor)
        self.collection.find.assert_called_once_with({})

    async def test_count_returns_amount(self):
        """Test that get_count method works and returns amount."""
        self.collection.count_documents.return_value = futurized(100)
        count = await self.test_service.get_count("test", {})
        self.collection.count_documents.assert_called_once_with({})
        self.assertEqual(count, 100)

    async def test_db_operation_is_retried_with_increasing_interval(self):
        """Patch timeout to be 0 sec instead of default, test autoreconnect."""
        self.collection.insert_one.side_effect = AutoReconnect
        with patch("metadata_backend.database.db_service.serverTimeout", 0):
            with self.assertRaises(ConnectionFailure):
                await self.test_service.create("test", self.data_stub)
        self.assertEqual(self.collection.insert_one.call_count, 5)
