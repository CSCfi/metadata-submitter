"""Test API endpoints from views module."""

from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from aiohttp.web import (
    HTTPBadRequest,
)

from metadata_backend.api.operators.file import File, FileOperator


class AsyncIterator:
    """Async iterator based on range."""

    def __init__(self, seq):
        """Init iterator with sequence."""
        self.iter = iter(seq)

    def __aiter__(self):
        """Return async iterator."""
        return self

    async def __anext__(self):
        """Get next element in sequence."""
        try:
            return next(self.iter)
        except StopIteration:
            raise StopAsyncIteration


class MockCursor(AsyncIterator):
    """Mock implementation of pymongo cursor.

    Takes iterable async mock and adds some pymongo cursor methods.
    """

    def __init__(self, seq) -> None:
        """Initialize cursor.

        :param seq: Iterable sequence
        """
        super().__init__(seq)
        self._skip = 0
        self._limit = 0

    def skip(self, count):
        """Set skip."""
        self._skip = count
        return self

    def limit(self, count):
        """Set limit."""
        self._limit = count if count != 0 else None
        return self


class TestOperators(IsolatedAsyncioTestCase):
    """Test db-operator classes."""

    def setUp(self):
        """Configure default values for testing and mock dbservice.

        Monkey patches MagicMock to work with async / await, then sets up
        other patches and mocks for tests.
        """
        self.client = MagicMock()
        self.project_id = "project_1000"
        self.project_generated_id = "64fbdce1c69b436e8d6c91fd746064d4"
        self.accession_id = uuid4().hex
        self.submission_id = uuid4().hex
        self.file_id = uuid4().hex
        self.test_submission = {
            "submissionId": self.submission_id,
            "projectId": self.project_generated_id,
            "name": "Mock submission",
            "description": "test mock submission",
            "published": False,
            "metadataObjects": [{"accessionId": "EGA1234567", "schema": "study"}],
        }
        self.test_submission_no_project = {
            "submissionId": self.submission_id,
            "name": "Mock submission",
            "description": "test mock submission",
            "published": False,
            "metadataObjects": [{"accessionId": "EGA1234567", "schema": "study"}],
        }
        self.test_file = {
            "name": "test-file.png",
            "accessionId": self.file_id,
            "path": "Bucket-name/subfolder/test-file.png",
            "projectId": self.project_id,
            "versions": [
                {
                    "version": 1,
                    "bytes": 3765457,
                    "encrypted_checksums": [
                        {"type": "sha256", "value": "82E4e60e73db2e06A00a079788F7d71f75b61a4b75f28c4c9427036d61234567"},
                        {"type": "md5", "value": "7Ac236b1a82dac89e7cf45d2b4812345"},
                    ],
                    "unencrypted_checksums": [
                        {"type": "sha256", "value": "82E4e60e73db2e06A00a079788F7d71f75b61a4b75f28c4c9427036d61234567"},
                        {"type": "md5", "value": "7Ac236b1a82dac89e7cf45d2b4812345"},
                    ],
                }
            ],
        }
        self.test_file_input = File(
            name=self.test_file["name"],
            path=self.test_file["path"],
            projectId=self.project_id,
            bytes=self.test_file["versions"][0]["bytes"],
            encrypted_checksums=self.test_file["versions"][0]["encrypted_checksums"],
            unencrypted_checksums=self.test_file["versions"][0]["unencrypted_checksums"],
        )
        self.file_operator = FileOperator(self.client)
        self.user_id = "current"
        self.user_generated_id = "5fb82fa1dcf9431fa5fcfb72e2d2ee14"
        self.test_user = {
            "userId": self.user_generated_id,
            "name": "tester",
        }
        class_dbservice = "metadata_backend.api.operators.base.DBService"
        self.patch_dbservice = patch(class_dbservice, spec=True)
        self.MockedDbService = self.patch_dbservice.start()

        self.patch_verify_authorization = patch(
            "metadata_backend.api.middlewares.verify_authorization",
            new=AsyncMock(return_value=("mock-userid", "mock-username")),
        )

    def tearDown(self):
        """Stop patchers."""
        self.patch_dbservice.stop()

    async def test_create_file_pass(self):
        """Test creating a new file passes."""
        self.file_operator.db_service.read_by_key_value = AsyncMock(return_value=None)
        self.file_operator.db_service.create = AsyncMock(return_value=True)

        file_info = await self.file_operator.create_file_or_version(self.test_file)
        self.assertEqual(file_info["accessionId"], self.file_id)
        self.assertEqual(file_info["version"], 1)

    async def test_create_file_version_pass(self):
        """Test creating new file version passes."""
        self.file_operator.db_service.patch = AsyncMock(return_value=True)
        new_test_file = self.test_file
        new_test_file["versions"][0]["version"] = 2
        file_info = await self.file_operator.create_file_or_version(new_test_file)
        self.assertEqual(file_info["accessionId"], self.file_id)
        self.assertEqual(file_info["version"], 2)

    async def test_create_file_version_fails(self):
        """Test creating new file version fails."""
        new_test_file = self.test_file
        new_test_file["versions"][0]["version"] = 0
        with self.assertRaises(HTTPBadRequest):
            await self.file_operator.create_file_or_version(new_test_file)

    async def test_form_validated_file_object(self):
        """Test forming a file object for inserting to db."""
        self.file_operator.db_service.read_by_key_value = AsyncMock(return_value=None)
        resp = await self.file_operator.form_validated_file_object(self.test_file_input)
        self.assertEqual(resp["path"], self.test_file["path"])
        self.assertEqual(resp["versions"][0]["version"], 1)
        self.assertFalse(resp["versions"][0]["published"])
        self.assertFalse(resp["flagDeleted"])

        # Test the same method with pre-existing file object in db
        file_in_db = {
            "accessionId": self.file_id,
            "currentVersion": {
                "version": 2,
                "bytes": 20,
                "submissions": ["s1"],
                "encrypted_checksums": [
                    {"type": "sha256", "value": "82E4e60e73db2e06A00a079788F7d71f75b61a4b75f28c4c9427036d61234567"},
                    {"type": "md5", "value": "7Ac236b1a82dac89e7cf45d2b4812345"},
                ],
                "unencrypted_checksums": [
                    {"type": "sha256", "value": "82E4e60e73db2e06A00a079788F7d71f75b61a4b75f28c4c9427036d61234567"},
                    {"type": "md5", "value": "7Ac236b1a82dac89e7cf45d2b4812345"},
                ],
            },
        }
        self.file_operator.db_service.read_by_key_value = AsyncMock(return_value=file_in_db)
        resp = await self.file_operator.form_validated_file_object(self.test_file_input)
        self.assertEqual(resp["path"], self.test_file["path"])
        self.assertEqual(resp["accessionId"], self.file_id)
        self.assertEqual(resp["versions"][0]["version"], 3)

    async def test_read_file(self):
        """Test reading file object from database passes."""
        file_list = [{"accessionId": "acc123456", "path": "s3:/bucket/files/mock", "name": "mock.file"}]
        self.file_operator.db_service.do_aggregate = AsyncMock(return_value=file_list)
        output = await self.file_operator.read_file(file_list[0]["accessionId"])
        self.assertEqual(file_list[0]["accessionId"], output["accessionId"])

        # With different file version as input
        output = await self.file_operator.read_file(file_list[0]["accessionId"], version=2)
        self.assertEqual(file_list[0]["accessionId"], output["accessionId"])

    async def test_read_project_files(self):
        """Test reading files from a project passes."""
        file_list = [
            {
                "accessionId": "acc123456",
            },
            {
                "accessionId": "acc456789",
            },
        ]
        self.file_operator.db_service.do_aggregate = AsyncMock(return_value=file_list)
        files = await self.file_operator.read_project_files("project_id1")
        self.assertEqual(file_list, files)

    async def test_flag_file_deleted(self):
        """Test file is flagged as deleted."""
        self.file_operator.db_service.update_by_key_value = AsyncMock(return_value=False)
        self.file_operator.remove_file_submission = AsyncMock(return_value=None)

        test_file = {
            "accessionId": "123",
            "path": "s3:/file/path",
            "projectId": "projectA",
        }
        with self.assertRaises(HTTPBadRequest):
            await self.file_operator.flag_file_deleted(test_file)

        self.file_operator.db_service.update_by_key_value = AsyncMock(return_value=True)
        await self.file_operator.flag_file_deleted(test_file, False)

    async def test_remove_file_submission(self):
        """Test removing file from a submission passes."""
        test_file = {
            "accessionId": "123",
            "path": "s3:/file/path",
            "projectId": "projectA",
        }
        with self.assertRaises(HTTPBadRequest):
            # Missing file_path or submission_id variable
            await self.file_operator.remove_file_submission(test_file["accessionId"])

        # Removing from all submission succeeds
        self.file_operator.db_service.read_by_key_value = AsyncMock(return_value=test_file)
        self.file_operator.db_service.remove_many = AsyncMock(return_value=True)
        await self.file_operator.remove_file_submission(test_file["accessionId"], test_file["path"])
        self.file_operator.db_service.remove_many.assert_called_once()

        # Removing from single submission but raises an error
        with self.assertRaises(HTTPBadRequest):
            self.file_operator.db_service.remove = AsyncMock(return_value=False)
            await self.file_operator.remove_file_submission("123", submission_id="submission_id1")
            self.file_operator.db_service.remove.assert_called_once()
