"""Test db_services."""
import unittest
import mongomock
from unittest.mock import patch

from metadata_backend.database.db_services import DBService


class DatabaseTestCase(unittest.TestCase):
    """Test different database operations."""

    def setUp(self):
        """Patch module level MongoClient variable with mongomock client."""
        variable_client = "metadata_backend.database.db_services.db_client"
        self.patch_client = patch(variable_client, mongomock.MongoClient())
        self.patch_client.start()

    def tearDown(self):
        """Cleanup mocked stuff."""
        self.patch_client.stop()

    def test_db_services_share_mongodb_client(self):
        """Test client is shared across different db_service_objects."""
        foo = DBService("foo")
        bar = DBService("bar")
        assert foo.database.client == bar.database.client
