"""Test db_services."""
from unittest.mock import MagicMock, patch, AsyncMock

from unittest import IsolatedAsyncioTestCase
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCursor
from pymongo.errors import AutoReconnect, ConnectionFailure
from pymongo.results import DeleteResult, InsertOneResult, UpdateResult

from metadata_backend.database.db_service import DBService
from pymongo import UpdateOne


class DatabaseTestCase(IsolatedAsyncioTestCase):
    """Test different database operations."""

    def setUp(self):
        """Initialize test service with mock client.

        Monkey patches MagicMock to work with async / await, then sets up
        client->database->collection -structure pymongo uses.

        Monkey patching can probably be removed when upgrading requirements to
        python 3.8+ since Mock 4.0+ library has async version of MagicMock.
        """
        self.client = MagicMock()
        self.database = MagicMock()
        self.collection = AsyncMock()
        self.client.__getitem__.return_value = self.database
        self.database.__getitem__.return_value = self.collection
        self.test_service = DBService("testdb", self.client)
        self.id_stub = "EGA123456"
        self.user_id_stub = "5fb82fa1dcf9431fa5fcfb72e2d2ee14"
        self.user_stub = {
            "userId": self.user_id_stub,
            "name": "name",
            "drafts": ["EGA123456", "EGA1234567"],
            "folders": ["EGA1234569"],
        }
        self.data_stub = {
            "accessionId": self.id_stub,
            "identifiers": ["foo", "bar"],
            "dateCreated": "2020-07-26T20:59:35.177Z",
        }
        self.f_id_stub = "FOL12345678"
        self.folder_stub = {
            "folderId": self.f_id_stub,
            "name": "test",
            "description": "test folder",
            "metadata_objects": ["EGA123456"],
        }

    def test_db_services_share_mongodb_client(self):
        """Test client is shared across different db_service_objects."""
        foo = DBService("foo", self.client)
        bar = DBService("bar", self.client)
        self.assertIs(foo.db_client, bar.db_client)

    async def test_create_inserts_data(self):
        """Test that create method works and returns success."""
        self.collection.insert_one.return_value = InsertOneResult(ObjectId("0123456789ab0123456789ab"), True)
        success = await self.test_service.create("testcollection", self.data_stub)
        self.collection.insert_one.assert_called_once_with(self.data_stub)
        self.assertTrue(success)

    async def test_create_reports_fail_correctly(self):
        """Test that failure is reported, when write not acknowledged."""
        self.collection.insert_one.return_value = InsertOneResult(None, False)
        success = await self.test_service.create("testcollection", self.data_stub)
        self.collection.insert_one.assert_called_once_with(self.data_stub)
        self.assertFalse(success)

    async def test_read_returns_data(self):
        """Test that read method works and returns data."""
        self.collection.find_one.return_value = self.data_stub
        found_doc = await self.test_service.read("testcollection", self.id_stub)
        self.assertEqual(found_doc, self.data_stub)
        self.collection.find_one.assert_called_once_with({"accessionId": self.id_stub}, {"_id": False})

    async def test_exists_returns_false(self):
        """Test that exists method works and returns false."""
        self.collection.find_one.return_value = None
        found_doc = await self.test_service.exists("testcollection", self.id_stub)
        self.assertEqual(found_doc, False)
        self.collection.find_one.assert_called_once_with({"accessionId": self.id_stub}, {"_id": False})

    async def test_exists_returns_true(self):
        """Test that exists method works and returns True."""
        self.collection.find_one.return_value = self.data_stub
        found_doc = await self.test_service.exists("testcollection", self.id_stub)
        self.assertEqual(found_doc, True)
        self.collection.find_one.assert_called_once_with({"accessionId": self.id_stub}, {"_id": False})

    async def test_update_updates_data(self):
        """Test that update method works and returns success."""
        self.collection.find_one.return_value = self.data_stub
        self.collection.update_one.return_value = UpdateResult({}, True)
        success = await self.test_service.update("testcollection", self.id_stub, self.data_stub)
        self.collection.update_one.assert_called_once_with({"accessionId": self.id_stub}, {"$set": self.data_stub})
        self.assertTrue(success)

    async def test_replace_replaces_data(self):
        """Test that replace method works and returns success."""
        self.collection.find_one.return_value = self.data_stub
        self.collection.replace_one.return_value = UpdateResult({}, True)
        success = await self.test_service.replace("testcollection", self.id_stub, self.data_stub)
        self.collection.replace_one.assert_called_once_with({"accessionId": self.id_stub}, self.data_stub)
        self.assertTrue(success)

    async def test_delete_deletes_data(self):
        """Test that delete method works and returns success."""
        self.collection.delete_one.return_value = DeleteResult({"n": 1}, True)
        success = await self.test_service.delete("testcollection", self.id_stub)
        self.collection.delete_one.assert_called_once_with({"accessionId": self.id_stub})
        self.assertTrue(success)

    def test_query_executes_find(self):
        """Test that find is executed, so cursor is returned."""
        self.collection.find.return_value = AsyncIOMotorCursor(None, None)
        self.test_service.query("testcollection", {})
        self.collection.find.assert_called_once_with({}, {"_id": False})

    async def test_count_returns_amount(self):
        """Test that get_count method works and returns amount."""
        self.collection.count_documents.return_value = 100
        count = await self.test_service.get_count("testcollection", {})
        self.collection.count_documents.assert_called_once_with({})
        self.assertEqual(count, 100)

    async def test_db_operation_is_retried_with_increasing_interval(self):
        """Patch timeout to be 0 sec instead of default, test autoreconnect."""
        self.collection.insert_one.side_effect = AutoReconnect
        with patch("metadata_backend.database.db_service.serverTimeout", 0):
            with self.assertRaises(ConnectionFailure):
                await self.test_service.create("testcollection", self.data_stub)
        self.assertEqual(self.collection.insert_one.call_count, 6)

    async def test_create_folder_inserts_folder(self):
        """Test that create method works for folder and returns success."""
        self.collection.insert_one.return_value = InsertOneResult(ObjectId("0000000000aa1111111111bb"), True)
        folder = await self.test_service.create("folder", self.folder_stub)
        self.collection.insert_one.assert_called_once_with(self.folder_stub)
        self.assertTrue(folder)

    async def test_read_folder_returns_data(self):
        """Test that read method works for folder and returns folder."""
        self.collection.find_one.return_value = self.folder_stub
        found_folder = await self.test_service.read("folder", self.f_id_stub)
        self.collection.find_one.assert_called_once_with({"folderId": self.f_id_stub}, {"_id": False})
        self.assertEqual(found_folder, self.folder_stub)

    async def test_published_folder_returns_data(self):
        """Test that published folder checks if folder is published."""
        self.collection.find_one.return_value = self.folder_stub
        found_folder = await self.test_service.published_folder(self.f_id_stub)
        self.collection.find_one.assert_called_once_with(
            {"published": True, "folderId": self.f_id_stub}, {"_id": False}
        )
        self.assertEqual(found_folder, True)

    async def test_externalId_exists_returns_false(self):
        """Test that externalId exists method works and returns None."""
        self.collection.find_one.return_value = None
        found_doc = await self.test_service.exists_user_by_externalId("test_user@eppn.fi", "name")
        self.assertEqual(found_doc, None)
        self.collection.find_one.assert_called_once_with(
            {"externalId": "test_user@eppn.fi", "name": "name"}, {"_id": False, "externalId": False}
        )

    async def test_externalId_exists_returns_true(self):
        """Test that externalId exists method works and returns user id."""
        self.collection.find_one.return_value = self.user_stub
        found_doc = await self.test_service.exists_user_by_externalId("test_user@eppn.fi", "name")
        self.assertEqual(found_doc, self.user_id_stub)
        self.collection.find_one.assert_called_once_with(
            {"externalId": "test_user@eppn.fi", "name": "name"}, {"_id": False, "externalId": False}
        )

    # async def test_aggregate_performed(self):
    #     """Test that aggregate is executed, so cursor is returned."""
    #     self.collection.aggregate.return_value = AsyncIterator(range(5))
    #     cursor = await self.test_service.do_aggregate("testcollection", [])
    #     self.assertEqual(type(cursor), list)
    #     self.collection.aggregate.assert_called_once_with([])

    async def test_append_data(self):
        """Test that append method works and returns data."""
        self.collection.find_one_and_update.return_value = self.data_stub
        success = await self.test_service.append("testcollection", self.id_stub, self.data_stub)
        self.collection.find_one_and_update.assert_called_once_with(
            {"accessionId": self.id_stub},
            {"$addToSet": self.data_stub},
            projection={"_id": False},
            return_document=True,
        )
        self.assertEqual(success, self.data_stub)

    async def test_remove_data(self):
        """Test that remove method works and returns data."""
        self.collection.find_one_and_update.return_value = {}
        success = await self.test_service.remove("testcollection", self.id_stub, self.data_stub)
        self.collection.find_one_and_update.assert_called_once_with(
            {"accessionId": self.id_stub},
            {"$pull": self.data_stub},
            projection={"_id": False},
            return_document=True,
        )
        self.assertEqual(success, {})

    async def test_patch_data(self):
        """Test that patch method works and returns data."""
        json_patch = [
            {"op": "add", "path": "/metadataObjects/-", "value": {"accessionId": self.id_stub, "schema": "study"}},
        ]
        self.collection.bulk_write.return_value = UpdateResult({}, True)
        success = await self.test_service.patch("testcollection", self.id_stub, json_patch)
        self.collection.bulk_write.assert_called_once_with(
            [
                UpdateOne(
                    {"testcollectionId": "EGA123456"},
                    {"$addToSet": {"metadataObjects": {"$each": [{"accessionId": "EGA123456", "schema": "study"}]}}},
                    False,
                    None,
                    None,
                    None,
                )
            ],
            ordered=False,
        )
        self.assertTrue(success)
