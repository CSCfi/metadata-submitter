"""Test API endpoints from views module."""

import datetime
import re
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

from aiohttp.web import (
    HTTPBadRequest,
    HTTPInternalServerError,
    HTTPMethodNotAllowed,
    HTTPNotFound,
    HTTPUnprocessableEntity,
)
from pymongo.errors import ConnectionFailure, OperationFailure

from metadata_backend.api.operators.file import File, FileOperator
from metadata_backend.api.operators.object import ObjectOperator
from metadata_backend.api.operators.object_xml import XMLObjectOperator
from metadata_backend.api.operators.submission import SubmissionOperator


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
        self.patch_accession = patch(
            "metadata_backend.api.operators.object.ObjectOperator._generate_accession_id",
            return_value=self.accession_id,
            autospec=True,
        )
        self.patch_accession.start()
        self.patch_submission = patch(
            "metadata_backend.api.operators.submission.SubmissionOperator._generate_accession_id",
            return_value=self.submission_id,
            autospec=True,
        )
        self.patch_submission.start()
        self.patch_file = patch(
            "metadata_backend.api.operators.file.FileOperator._generate_accession_id",
            return_value=self.file_id,
            autospec=True,
        )
        self.patch_file.start()

        self.patch_verify_authorization = patch(
            "metadata_backend.api.middlewares.verify_authorization",
            new=AsyncMock(return_value=("mock-userid", "mock-username")),
        )

    def tearDown(self):
        """Stop patchers."""
        self.patch_dbservice.stop()
        self.patch_accession.stop()
        self.patch_submission.stop()
        self.patch_file.stop()

    async def test_reading_metadata_works(self):
        """Test JSON is read from db correctly."""
        operator = ObjectOperator(self.client)
        data = {
            "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
            "dateModified": datetime.datetime(2020, 6, 14, 0, 0),
            "accessionId": "EGA123456",
            "foo": "bar",
        }
        operator.db_service.read = AsyncMock(return_value=data)
        read_data, c_type = await operator.read_metadata_object("sample", "EGA123456")
        operator.db_service.read.assert_called_once_with("sample", "EGA123456")
        self.assertEqual(c_type, "application/json")
        self.assertEqual(
            read_data,
            {
                "dateCreated": "2020-06-14T00:00:00",
                "dateModified": "2020-06-14T00:00:00",
                "accessionId": "EGA123456",
                "foo": "bar",
            },
        )

    async def test_reading_metadata_works_with_xml(self):
        """Test XML is read from db correctly."""
        operator = XMLObjectOperator(self.client)
        data = {"accessionId": "EGA123456", "content": "<MOCK_ELEM></MOCK_ELEM>"}
        operator.db_service.read = AsyncMock(return_value=data)
        r_data, c_type = await operator.read_metadata_object("sample", "EGA123456")
        operator.db_service.read.assert_called_once_with("sample", "EGA123456")
        self.assertEqual(c_type, "text/xml")
        self.assertEqual(r_data, data["content"])

    async def test_reading_with_non_valid_id_raises_error(self):
        """Test read metadata HTTPNotFound is raised."""
        operator = ObjectOperator(self.client)
        operator.db_service.read = AsyncMock(return_value=False)
        with self.assertRaises(HTTPNotFound):
            await operator.read_metadata_object("study", "EGA123456")

    async def test_db_error_raises_400_error(self):
        """Test read metadata HTTPBadRequest is raised."""
        operator = ObjectOperator(self.client)
        operator.db_service.read.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.read_metadata_object("study", "EGA123456")

    def test_operator_fixes_single_document_presentation(self):
        """Test datetime is fixed and id removed."""
        study_test = {
            "publishDate": datetime.datetime(2020, 6, 14, 0, 0),
            "accessionId": "EDAG3945644754983408",
            "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
            "dateModified": datetime.datetime(2020, 6, 14, 0, 0),
        }
        result = ObjectOperator(self.client)._format_single_dict("study", study_test)
        self.assertEqual(result["publishDate"], "2020-06-14T00:00:00")
        self.assertEqual(result["dateCreated"], "2020-06-14T00:00:00")
        self.assertEqual(result["dateModified"], "2020-06-14T00:00:00")
        with self.assertRaises(KeyError):
            result["_Id"]

    async def test_json_create_passes_and_returns_accessionId(self):
        """Test create method for JSON works."""
        operator = ObjectOperator(self.client)
        data = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {"studyTitle": "Highly", "studyType": "Other"},
        }
        operator.db_service.create = AsyncMock(return_value=True)
        data = await operator.create_metadata_object("study", data)
        operator.db_service.create.assert_called_once()
        self.assertEqual(data["accessionId"], self.accession_id)

    async def test_create_bp_metadata_object(self):
        """Test that creating a BP metadata object works.

        Accession id of created object should be in BP format.
        """
        operator = ObjectOperator(self.client)
        bp_image_data = {
            "imageOf": [{"alias": "image_alias"}],
            "imageType": "wsiImage",
            "files": [
                {
                    "fileType": "dsm",
                    "fileName": "testFileName",
                    "checksumMethod": "SHA256",
                    "checksum": "f2ca1bb6c7e907d06dafe4687e579fce76b37e4e93b7605022da52e6ccc26fd2",
                }
            ],
        }
        operator.db_service.create = AsyncMock(return_value=True)
        data = await operator.create_metadata_object("bpimage", bp_image_data)
        operator.db_service.create.assert_called_once()
        bp_id_pattern = re.compile("^bb-image(-[a-hj-knm-z23456789]{6}){2}$")
        self.assertTrue(bp_id_pattern.match(data["accessionId"]))

    async def test_json_replace_passes_and_returns_accessionId(self):
        """Test replace method for JSON works."""
        data = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {"studyTitle": "Highly", "studyType": "Other"},
        }
        operator = ObjectOperator(self.client)
        operator.db_service.exists = AsyncMock(return_value=True)
        operator.db_service.replace = AsyncMock(return_value=True)
        data = await operator.replace_metadata_object("study", self.accession_id, data)
        operator.db_service.replace.assert_called_once()
        self.assertEqual(data["accessionId"], self.accession_id)

    async def test_json_replace_raises_if_not_exists(self):
        """Test replace method raises error."""
        operator = ObjectOperator(self.client)
        operator.db_service.exists = AsyncMock(return_value=False)
        operator.db_service.replace = AsyncMock(return_value=True)
        with self.assertRaises(HTTPNotFound):
            await operator.replace_metadata_object("study", self.accession_id, {})
            operator.db_service.replace.assert_called_once()

    async def test_db_error_replace_raises_400_error(self):
        """Test replace metadata HTTPBadRequest is raised."""
        operator = ObjectOperator(self.client)
        operator.db_service.exists.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.replace_metadata_object("study", self.accession_id, {})

    async def test_json_update_passes_and_returns_accessionId(self):
        """Test update method for JSON works."""
        data = {"centerName": "GEOM", "alias": "GSE10967"}
        db_data = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {"studyTitle": "Highly", "studyType": "Other"},
        }
        operator = ObjectOperator(self.client)
        operator.db_service.read.return_value = db_data
        operator.db_service.exists = AsyncMock(return_value=True)
        operator.db_service.update = AsyncMock(return_value=True)
        accession = await operator.update_metadata_object("study", self.accession_id, data)
        operator.db_service.update.assert_called_once()
        self.assertEqual(accession, self.accession_id)

    async def test_json_update_raises_if_not_exists(self):
        """Test update method raises error."""
        operator = ObjectOperator(self.client)
        operator.db_service.exists = AsyncMock(return_value=False)
        with self.assertRaises(HTTPNotFound):
            await operator.update_metadata_object("study", self.accession_id, {})
            operator.db_service.update.assert_called_once()

    async def test_db_error_update_raises_400_error(self):
        """Test update metadata HTTPBadRequest is raised."""
        operator = ObjectOperator(self.client)
        operator.db_service.exists.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.update_metadata_object("study", self.accession_id, {})

    async def test_xml_create_passes_and_returns_accessionId(self):
        """Test create method for XML works. Patch JSON related calls."""
        operator = XMLObjectOperator(self.client)
        operator.db_service.db_client = self.client
        operator.db_service.create.return_value = True
        operator.db_service.create = AsyncMock(return_value=True)
        xml_data = "<MOCK_ELEM></MOCK_ELEM>"
        with patch(
            ("metadata_backend.api.operators.object.ObjectOperator._format_data_to_create_and_add_to_db"),
            return_value={"accessionId": self.accession_id},
        ):
            with patch(
                ("metadata_backend.api.operators.object_xml.XMLToJSONParser.parse"),
                return_value=({"mockElem": None}, [xml_data]),
            ):
                data = await operator.create_metadata_object("study", xml_data)
        operator.db_service.create.assert_called_once()
        self.assertEqual(data[0]["accessionId"], self.accession_id)

    async def test_correct_data_is_set_to_json_when_creating(self):
        """Test operator creates object and adds necessary info."""
        operator = ObjectOperator(self.client)
        with patch(
            ("metadata_backend.api.operators.object.ObjectOperator._insert_formatted_object_to_db"),
            return_value=True,
        ) as mocked_insert:
            with patch("metadata_backend.api.operators.object.datetime") as m_date:
                m_date.now.return_value = datetime.datetime(2020, 4, 14)
                acc = await operator._format_data_to_create_and_add_to_db("study", {})
                mocked_insert.assert_called_once_with(
                    "study",
                    {
                        "accessionId": self.accession_id,
                        "dateCreated": datetime.datetime(2020, 4, 14),
                        "dateModified": datetime.datetime(2020, 4, 14),
                        "publishDate": datetime.datetime(2020, 6, 14),
                    },
                )
            self.assertEqual(acc["accessionId"], self.accession_id)

    async def test_correct_data_is_set_to_json_when_replacing(self):
        """Test operator replaces object and adds necessary info."""
        operator = ObjectOperator(self.client)
        with patch(
            "metadata_backend.api.operators.object.ObjectOperator._replace_object_from_db",
            return_value=self.accession_id,
        ) as mocked_insert:
            with patch("metadata_backend.api.operators.object.datetime") as m_date:
                m_date.now.return_value = datetime.datetime(2020, 4, 14)
                self.MockedDbService().read.return_value = {
                    "accessionId": self.accession_id,
                    "dateModified": datetime.datetime(2020, 4, 14),
                }
                acc = await operator._format_data_to_replace_and_add_to_db("study", self.accession_id, {})
                mocked_insert.assert_called_once_with(
                    "study",
                    self.accession_id,
                    {"accessionId": self.accession_id, "dateModified": datetime.datetime(2020, 4, 14)},
                )
            self.assertEqual(acc["accessionId"], self.accession_id)

    async def test_wrong_data_is_set_to_json_when_replacing(self):
        """Test operator replace catches error."""
        operator = ObjectOperator(self.client)
        with patch(
            "metadata_backend.api.operators.object.ObjectOperator._replace_object_from_db",
            return_value=self.accession_id,
        ):
            with patch("metadata_backend.api.operators.object.datetime") as m_date:
                m_date.now.return_value = datetime.datetime(2020, 4, 14)
                with self.assertRaises(HTTPBadRequest):
                    await operator._format_data_to_replace_and_add_to_db(
                        "study",
                        self.accession_id,
                        {
                            "accessionId": self.accession_id,
                            "dateCreated": datetime.datetime(2020, 4, 14),
                            "dateModified": datetime.datetime(2020, 4, 14),
                            "publishDate": datetime.datetime(2020, 6, 14),
                        },
                    )

    async def test_correct_data_is_set_to_json_when_updating(self):
        """Test operator updates object and adds necessary info."""
        operator = ObjectOperator(self.client)
        with patch(
            ("metadata_backend.api.operators.object.ObjectOperator._update_object_from_db"),
            return_value=self.accession_id,
        ) as mocked_insert:
            with patch("metadata_backend.api.operators.object.datetime") as m_date:
                m_date.now.return_value = datetime.datetime(2020, 4, 14)
                acc = await operator._format_data_to_update_and_add_to_db("study", self.accession_id, {})
                mocked_insert.assert_called_once_with(
                    "study",
                    self.accession_id,
                    {"accessionId": self.accession_id, "dateModified": datetime.datetime(2020, 4, 14)},
                )
            self.assertEqual(acc, self.accession_id)

    async def test_wrong_data_is_set_to_json_when_updating(self):
        """Test operator update catches error."""
        operator = ObjectOperator(self.client)
        with patch(
            ("metadata_backend.api.operators.object.ObjectOperator._update_object_from_db"),
            return_value=self.accession_id,
        ):
            with patch("metadata_backend.api.operators.object.datetime") as m_date:
                m_date.now.return_value = datetime.datetime(2020, 4, 14)
                with self.assertRaises(HTTPBadRequest):
                    await operator._format_data_to_update_and_add_to_db(
                        "study",
                        self.accession_id,
                        {
                            "accessionId": self.accession_id,
                            "dateCreated": datetime.datetime(2020, 4, 14),
                            "dateModified": datetime.datetime(2020, 4, 14),
                            "publishDate": datetime.datetime(2020, 6, 14),
                        },
                    )

    async def test_correct_data_is_set_to_xml_when_creating(self):
        """Test XMLoperator creates object and adds necessary info."""
        operator = XMLObjectOperator(self.client)
        operator.db_service.db_client = self.client
        xml_data = "<MOCK_ELEM></MOCK_ELEM>"
        with patch(
            ("metadata_backend.api.operators.object.ObjectOperator._format_data_to_create_and_add_to_db"),
            return_value={"accessionId": self.accession_id},
        ):
            with patch(
                ("metadata_backend.api.operators.object_xml.XMLObjectOperator._insert_formatted_object_to_db"),
                return_value=True,
            ) as m_insert:
                with patch(
                    ("metadata_backend.api.operators.object_xml.XMLToJSONParser.parse"),
                    return_value=({"mockElem": None}, [xml_data]),
                ):
                    acc = await operator._format_data_to_create_and_add_to_db("study", xml_data)
                    m_insert.assert_called_once_with(
                        "xml-study", {"accessionId": self.accession_id, "content": xml_data}
                    )
                    self.assertEqual(acc[0]["accessionId"], self.accession_id)

    async def test_correct_data_is_set_to_xml_when_replacing(self):
        """Test XMLoperator replaces object and adds necessary info."""
        operator = XMLObjectOperator(self.client)
        operator.db_service.db_client = self.client
        xml_data = "<MOCK_ELEM></MOCK_ELEM>"
        with patch(
            "metadata_backend.api.operators.object.ObjectOperator._format_data_to_replace_and_add_to_db",
            return_value={"accessionId": self.accession_id},
        ):
            with patch(
                "metadata_backend.api.operators.object_xml.XMLObjectOperator._replace_object_from_db",
                return_value=self.accession_id,
            ) as m_insert:
                with patch(
                    "metadata_backend.api.operators.object_xml.XMLToJSONParser.parse",
                    return_value=({"mockElem": None}, [xml_data]),
                ):
                    acc = await operator._format_data_to_replace_and_add_to_db("study", self.accession_id, xml_data)
                    m_insert.assert_called_once_with(
                        "xml-study",
                        self.accession_id,
                        {"accessionId": self.accession_id, "content": xml_data},
                    )
                    self.assertEqual(acc["accessionId"], self.accession_id)

    async def test_deleting_metadata_deletes_json(self):
        """Test metadata is deleted."""
        operator = ObjectOperator(self.client)
        operator.db_service.db_client = self.client
        operator.db_service.exists = AsyncMock(return_value=True)
        operator.db_service.delete = AsyncMock(return_value=True)
        await operator.delete_metadata_object("sample", "EGA123456")
        self.assertEqual(operator.db_service.delete.call_count, 1)
        operator.db_service.delete.assert_called_with("sample", "EGA123456")

    async def test_deleting_metadata_delete_raises(self):
        """Test error raised with delete."""
        operator = ObjectOperator(self.client)
        operator.db_service.db_client = self.client
        operator.db_service.exists = AsyncMock(return_value=False)
        operator.db_service.delete = AsyncMock(return_value=True)
        with self.assertRaises(HTTPNotFound):
            await operator.delete_metadata_object("sample", "EGA123456")
            self.assertEqual(operator.db_service.delete.call_count, 1)
            operator.db_service.delete.assert_called_with("sample", "EGA123456")

    async def test_deleting_metadata_delete_raises_bad_request(self):
        """Test bad request error raised with delete."""
        operator = ObjectOperator(self.client)
        operator.db_service.db_client = self.client
        operator.db_service.exists = AsyncMock(return_value=True)
        operator.db_service.delete = AsyncMock(return_value=False)
        with self.assertRaises(HTTPBadRequest):
            await operator.delete_metadata_object("sample", "EGA123456")
            self.assertEqual(operator.db_service.delete.call_count, 1)
            operator.db_service.delete.assert_called_with("sample", "EGA123456")

    async def test_query_by_alias(self):
        """Test that database query by alias works."""
        operator = ObjectOperator(self.client)
        alias = "test"
        operator.db_service.query.return_value = AsyncIterator([{"alias": alias}])
        await operator.query_by_alias("study", alias)
        operator.db_service.query.assert_has_calls([call('study', {'alias': 'test'})])

    async def test_get_submission_field_db_fail(self):
        """Test get submission projectId, db connection and operation failure."""
        operator = SubmissionOperator(self.client)
        operator.db_service.query.side_effect = ConnectionFailure
        with self.assertRaises(HTTPInternalServerError):
            await operator.get_submission_field(self.submission_id, "projectId")

        operator.db_service.query.side_effect = OperationFailure("err")
        with self.assertRaises(HTTPInternalServerError):
            await operator.get_submission_field(self.submission_id, "projectId")

    async def test_get_submission_field_passes(self):
        """Test get submission projectId returns project id."""
        operator = SubmissionOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([self.test_submission])
        result = await operator.get_submission_field(self.submission_id, "projectId")
        operator.db_service.query.assert_called_once_with(
            "submission", {"submissionId": self.submission_id}, {"_id": False, "projectId": 1}, limit=1
        )
        self.assertEqual(result, self.project_generated_id)

    async def test_get_submission_field_fails(self):
        """Test get submission projectId raises an error."""
        operator = SubmissionOperator(self.client)
        # Submission is not found error
        operator.db_service.query.return_value = AsyncIterator([])
        with self.assertRaises(HTTPBadRequest):
            await operator.get_submission_field(self.submission_id, "projectId")

        # Submission doesn't have projectId
        operator.db_service.query.return_value = AsyncIterator([self.test_submission_no_project])
        with self.assertRaises(HTTPBadRequest):
            await operator.get_submission_field(self.submission_id, "projectId")

    async def test_get_submission_field_string(self):
        """Test get submission field string."""
        operator = SubmissionOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([self.test_submission])
        result = await operator.get_submission_field(self.submission_id, "projectId")
        self.assertEqual(result, self.project_generated_id)

        # Raises an error when field is not a string
        operator.db_service.query.return_value = AsyncIterator([self.test_submission])
        with self.assertRaises(HTTPInternalServerError):
            await operator.get_submission_field_str(self.submission_id, "metadataObjects")

    async def test_get_submission_field_list(self):
        """Test get submission field list."""
        operator = SubmissionOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([self.test_submission])
        result = await operator.get_submission_field_list(self.submission_id, "metadataObjects")
        self.assertEqual(result, [{"accessionId": "EGA1234567", "schema": "study"}])

        # Raises an error when field is not a list
        operator.db_service.query.return_value = AsyncIterator([self.test_submission])
        with self.assertRaises(HTTPInternalServerError):
            await operator.get_submission_field_list(self.submission_id, "projectId")

    async def test_create_submission_works_and_returns_submissionId(self):
        """Test create method for submissions work."""
        operator = SubmissionOperator(self.client)
        data = {"name": "Mock submission", "description": "test mock submission"}
        operator.db_service.create = AsyncMock(return_value=True)
        submission = await operator.create_submission(data)
        operator.db_service.create.assert_called_once()
        self.assertEqual(submission, self.submission_id)

    async def test_create_submission_fails(self):
        """Test create method for submissions fails."""
        operator = SubmissionOperator(self.client)
        data = {"name": "Mock submission", "description": "test mock submission"}
        operator.db_service.create.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.create_submission(data)

    async def test_create_submission_db_create_fails(self):
        """Test create method for submissions db create fails."""
        operator = SubmissionOperator(self.client)
        data = {"name": "Mock submission", "description": "test mock submission"}
        operator.db_service.create = AsyncMock(return_value=False)
        with self.assertRaises(HTTPBadRequest):
            await operator.create_submission(data)

    async def test_query_submissions_empty_list(self):
        """Test query returns empty list."""
        operator = SubmissionOperator(self.client)
        operator.db_service.do_aggregate = AsyncMock(side_effect=([], [{"total": 0}]))
        submissions = await operator.query_submissions({}, 1, 5)
        operator.db_service.do_aggregate.assert_called()
        self.assertEqual(submissions, ([], 0))

    async def test_query_submissions_1_item(self):
        """Test query returns a list with item."""
        operator = SubmissionOperator(self.client)
        operator.db_service.do_aggregate = AsyncMock(side_effect=([{"name": "submission"}], [{"total": 1}]))
        submissions = await operator.query_submissions({}, 1, 5)
        operator.db_service.do_aggregate.assert_called()
        self.assertEqual(submissions, ([{"name": "submission"}], 1))

    async def test_check_object_submission_fails(self):
        """Test check object submission fails."""
        operator = SubmissionOperator(self.client)
        self.MockedDbService().query.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.check_object_in_submission("study", self.accession_id)

    async def test_check_object_submission_passes(self):
        """Test check object submission returns proper data."""
        operator = SubmissionOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([self.test_submission])
        result = await operator.check_object_in_submission("study", self.accession_id)
        operator.db_service.query.assert_called_once_with(
            "submission", {"metadataObjects": {"$elemMatch": {"accessionId": self.accession_id, "schema": "study"}}}
        )
        self.assertEqual(result, (self.submission_id, False))

    async def test_check_object_submission_multiple_objects_fails(self):
        """Test check object submission returns multiple unique submissions."""
        operator = SubmissionOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([self.test_submission, self.test_submission])
        with self.assertRaises(HTTPUnprocessableEntity):
            await operator.check_object_in_submission("study", self.accession_id)
            operator.db_service.query.assert_called_once_with(
                "submission", {"metadataObjects": {"$elemMatch": {"accessionId": self.accession_id, "schema": "study"}}}
            )

    async def test_check_object_submission_no_data(self):
        """Test check object submission returns no data."""
        operator = SubmissionOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([])
        result = await operator.check_object_in_submission("study", self.accession_id)
        operator.db_service.query.assert_called_once_with(
            "submission", {"metadataObjects": {"$elemMatch": {"accessionId": self.accession_id, "schema": "study"}}}
        )
        self.assertEqual(result, ("", False))

    async def test_check_object_submission_published(self):
        """Test check object submission is published."""
        operator = SubmissionOperator(self.client)
        alt_test_submission = self.test_submission
        alt_test_submission["published"] = True
        operator.db_service.query.return_value = AsyncIterator([alt_test_submission])
        result = await operator.check_object_in_submission("study", self.accession_id)
        operator.db_service.query.assert_called_once_with(
            "submission", {"metadataObjects": {"$elemMatch": {"accessionId": self.accession_id, "schema": "study"}}}
        )
        self.assertEqual(result, (self.submission_id, True))

    async def test_get_objects_submission_fails(self):
        """Test check object submission fails."""
        operator = SubmissionOperator(self.client)
        operator.db_service.query.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.get_collection_objects(self.submission_id, "study")

    async def test_get_objects_submission_passes(self):
        """Test get objects from submission returns proper data."""
        operator = SubmissionOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([self.test_submission])
        result = await operator.get_collection_objects(self.submission_id, "study")
        operator.db_service.query.assert_called_once_with(
            "submission",
            {"$and": [{"metadataObjects": {"$elemMatch": {"schema": "study"}}}, {"submissionId": self.submission_id}]},
        )
        self.assertEqual(result, ["EGA1234567"])

    async def test_get_objects_submission_no_data(self):
        """Test get objects from submission returns no data."""
        operator = SubmissionOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([])
        result = await operator.get_collection_objects(self.submission_id, "study")
        operator.db_service.query.assert_called_once_with(
            "submission",
            {"$and": [{"metadataObjects": {"$elemMatch": {"schema": "study"}}}, {"submissionId": self.submission_id}]},
        )
        self.assertEqual(result, [])

    async def test_reading_submission_works(self):
        """Test submission is read from db correctly."""
        operator = SubmissionOperator(self.client)
        operator.db_service.read = AsyncMock(return_value=self.test_submission)
        read_data = await operator.read_submission(self.submission_id)
        operator.db_service.read.assert_called_once_with("submission", self.submission_id)
        self.assertEqual(read_data, self.test_submission)

    async def test_submission_object_read_fails(self):
        """Test submission read fails."""
        operator = SubmissionOperator(self.client)
        operator.db_service.read.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.read_submission(self.submission_id)

    async def test_submission_update_passes_and_returns_id(self):
        """Test update method for submissions works."""
        patch = [{"op": "add", "path": "/name", "value": "test2"}]
        operator = SubmissionOperator(self.client)
        operator.db_service.patch = AsyncMock(return_value=True)
        submission = await operator.update_submission(self.test_submission, patch)
        operator.db_service.patch.assert_called_once()
        self.assertEqual(submission["submissionId"], self.submission_id)

    async def test_submission_update_fails_with_bad_patch(self):
        """Test submission update raises error with improper JSON Patch."""
        patch = [{"op": "replace", "path": "/nothing"}]
        operator = SubmissionOperator(self.client)
        operator.db_service.patch = AsyncMock(return_value=False)
        with self.assertRaises(HTTPBadRequest):
            await operator.update_submission(self.test_submission, patch)

    async def test_submission_object_update_fails(self):
        """Test submission update fails."""
        operator = SubmissionOperator(self.client)
        operator.db_service.patch.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.update_submission(self.test_submission, [])

    async def test_submission_object_remove_passes(self):
        """Test remove object method for submissions works."""
        operator = SubmissionOperator(self.client)
        operator.db_service.remove = AsyncMock(return_value=self.test_submission)
        await operator.remove_object(self.test_submission, "study", self.accession_id)
        operator.db_service.remove.assert_called_once()
        self.assertEqual(len(operator.db_service.remove.mock_calls), 1)

    async def test_submission_object_remove_fails(self):
        """Test submission remove object fails."""
        operator = SubmissionOperator(self.client)
        operator.db_service.remove.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.remove_object(self.test_submission, "study", self.accession_id)

    async def test_check_submission_exists_passes(self):
        """Test submission existance check passes."""
        operator = SubmissionOperator(self.client)
        operator.db_service.exists = AsyncMock(return_value=True)
        await operator.check_submission_exists(self.submission_id)
        operator.db_service.exists.assert_called_once()

    async def test_check_submission_exists_fails(self):
        """Test submission existance check fails."""
        operator = SubmissionOperator(self.client)
        operator.db_service.exists = AsyncMock(return_value=False)
        with self.assertRaises(HTTPNotFound):
            await operator.check_submission_exists(self.submission_id)
            operator.db_service.exists.assert_called_once()

    async def test_check_submission_published_passes(self):
        """Test submission published check passes."""
        operator = SubmissionOperator(self.client)
        operator.db_service.published_submission = AsyncMock(return_value=False)
        await operator.check_submission_published(self.submission_id, "PATCH")
        operator.db_service.published_submission.assert_called_once()

    async def test_check_submission_published_fails(self):
        """Test submission published check fails."""
        operator = SubmissionOperator(self.client)
        operator.db_service.published_submission = AsyncMock(return_value=True)
        with self.assertRaises(HTTPMethodNotAllowed) as context:
            await operator.check_submission_published(self.submission_id, "PATCH")
            operator.db_service.published_submission.assert_called_once()
        self.assertEqual("PATCH", context.exception.method)
        self.assertEqual({"GET", "HEAD"}, context.exception.allowed_methods)

    async def test_deleting_submission_passes(self):
        """Test submission is deleted correctly, if not published."""
        operator = SubmissionOperator(self.client)
        operator.db_service.published_submission = AsyncMock(return_value=False)
        operator.db_service.delete = AsyncMock(return_value=True)
        await operator.delete_submission(self.submission_id)
        operator.db_service.delete.assert_called_with("submission", self.submission_id)

    async def test_deleting_submission_fails_on_delete(self):
        """Test submission fails on db delete, if not published."""
        operator = SubmissionOperator(self.client)
        operator.db_service.published_submission = AsyncMock(return_value=False)
        operator.db_service.delete = AsyncMock(return_value=False)
        with self.assertRaises(HTTPBadRequest):
            await operator.delete_submission(self.submission_id)
            operator.db_service.delete.assert_called_with("submission", self.submission_id)

    async def test_delete_submission_fails(self):
        """Test submission delete fails."""
        operator = SubmissionOperator(self.client)
        operator.db_service.delete.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.delete_submission(self.submission_id)

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

    async def test_check_submission_files_ready(self):
        """Test files are marked as ready in a submission."""
        # DB query doesn't find problematic files
        self.file_operator.db_service.do_aggregate = AsyncMock(return_value=[])
        await self.file_operator.check_submission_files_ready("submission_id1")

        # DB query returns problematic files and raises error
        self.file_operator.db_service.do_aggregate = AsyncMock(return_value=[{"accessionId": "123"}])
        with self.assertRaises(HTTPBadRequest):
            await self.file_operator.check_submission_files_ready("submission_id1")

    async def test_read_submission_files(self):
        """Test getting files in a submission passes."""
        self.file_operator.db_service.do_aggregate = AsyncMock(return_value={})
        with self.assertRaises(HTTPInternalServerError):
            await self.file_operator.read_submission_files("submission_id1")

        self.file_operator.db_service.do_aggregate = AsyncMock(return_value=[])
        file_list = await self.file_operator.read_submission_files("submission_id1")
        self.assertEqual(file_list, [])

        example_list = [
            {
                "accessionId": "123",
                "version": 1,
            },
        ]
        self.file_operator.db_service.do_aggregate = AsyncMock(return_value=example_list)
        file_list = await self.file_operator.read_submission_files("submission_id1", ["added"])
        self.assertEqual(file_list, example_list)

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

    async def test_update_file_submission(self):
        """Test updating file submissions passes."""
        self.file_operator.db_service.update_by_key_value = AsyncMock(return_value=True)
        await self.file_operator.update_file_submission("accession123", "submission1", {"$set": "something"})

        self.file_operator.db_service.update_by_key_value = AsyncMock(return_value=False)
        with self.assertRaises(HTTPBadRequest):
            await self.file_operator.update_file_submission("accession123", "submission1", {"$set": "something"})

    async def test_check_submission_has_file(self):
        """Test checking submission has a file."""
        self.file_operator.db_service.read = AsyncMock(return_value=None)
        resp = await self.file_operator.check_submission_has_file("submission1", "123")
        self.assertFalse(resp)

        submission = {
            "files": [
                {
                    "accessionId": "123",
                },
                {
                    "accessionId": "456",
                },
            ]
        }
        self.file_operator.db_service.read = AsyncMock(return_value=submission)
        resp = await self.file_operator.check_submission_has_file("submission1", "123")
        self.assertTrue(resp)
