"""Test db_services."""
import copy
import unittest
import mongomock

from metadata_backend.database.db_service import DBService


class DatabaseTestCase(unittest.TestCase):
    """Test different database operations."""

    def setUp(self):
        """Setup test service with mongomock client."""
        self.test_service = DBService("test", mongomock.MongoClient())

    def test_db_services_share_mongodb_client(self):
        """Test client is shared across different db_service_objects."""
        foo = DBService("foo", mongomock.MongoClient())
        bar = DBService("bar", mongomock.MongoClient())
        assert foo.database.client == bar.database.client

    async def test_crud_create_and_read_works(self):
        """Test that basic crud stuff works as expected."""
        data = {"accessionId": "EGA123456",
                'identifiers': {'primaryId': 'ERR000076',
                                'submitterId': {
                                    'attributes': {'namespace': 'BGI'},
                                    'children': ['BGI-FC304RWAAXX']}}}
        # Since mongomock is essentially in-memory mongodb, we want to use
        # copies to avoid side effects
        await self.test_service.create("test", copy.deepcopy(data))
        # Read
        results = self.test_service.read("test", "EGA123456")
        del results["_id"]
        assert results == data

    def test_crud_update_works(self):
        """Test that update operation works as expected."""
        data = {"accessionId": "EGA123456",
                'identifiers': {'primaryId': 'ERR000076',
                                'submitterId': {
                                    'attributes': {'namespace': 'BGI'},
                                    'children': ['BGI-FC304RWAAXX']}}}
        self.test_service.create("test", copy.deepcopy(data))
        # Update
        update_data = {"identifiers.submitterId.attributes.namespace": "ABC"}
        self.test_service.update("test", "EGA123456", update_data)
        # Read
        results = self.test_service.read("test", "EGA123456")
        del results["_id"]
        goal_data = {"accessionId": "EGA123456",
                     'identifiers': {'primaryId': 'ERR000076',
                                     'submitterId': {
                                         'attributes': {'namespace': 'ABC'},
                                         'children': ['BGI-FC304RWAAXX']}}}
        assert results == goal_data

    def test_crud_replace_works(self):
        """Test that replace operation works as expected."""
        data = {"accessionId": "EGA123456",
                'identifiers': {'primaryId': 'ERR000076',
                                'submitterId': {
                                    'attributes': {'namespace': 'BGI'},
                                    'children': ['BGI-FC304RWAAXX']}}}
        self.test_service.create("test", copy.deepcopy(data))
        # Update
        new_data = {"accessionId": "EGA123456",
                    'identifiers': {'primaryId': 'ERNMAGE111',
                                    'foo': 'bar'}}
        self.test_service.replace("test", "EGA123456", copy.deepcopy(new_data))
        # Read
        results = self.test_service.read("test", "EGA123456")
        del results["_id"]
        assert results == new_data

    def test_crud_delete_works(self):
        """Test that replace operation works as expected."""
        data = {"accessionId": "EGA123456",
                'identifiers': {'primaryId': 'ERR000076',
                                'submitterId': {
                                    'attributes': {'namespace': 'BGI'},
                                    'children': ['BGI-FC304RWAAXX']}}}
        self.test_service.create("test", copy.deepcopy(data))
        self.test_service.delete("test", "EGA123456")
        # Read
        results = self.test_service.read("test", "EGA123456")
        assert results is None
