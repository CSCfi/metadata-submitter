"""Test API endpoints from views module."""

import datetime
import re
import time
import unittest
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import aiohttp_session
from aiohttp.test_utils import make_mocked_coro
from aiohttp.web import (
    HTTPBadRequest,
    HTTPInternalServerError,
    HTTPMethodNotAllowed,
    HTTPNotFound,
    HTTPUnprocessableEntity,
)
from multidict import MultiDict, MultiDictProxy
from pymongo.errors import ConnectionFailure, OperationFailure

from metadata_backend.api.operators.file import File, FileOperator
from metadata_backend.api.operators.object import ObjectOperator
from metadata_backend.api.operators.object_xml import XMLObjectOperator
from metadata_backend.api.operators.project import ProjectOperator
from metadata_backend.api.operators.submission import SubmissionOperator
from metadata_backend.api.operators.user import UserOperator

from .mockups import Mock_Request


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
        self.test_file = File(
            name="test-file.png",
            path="Bucket-name/subfolder/test-file.png",
            bytes=3765457,
            project=self.project_id,
            encrypted_checksums=[
                {"type": "sha256", "value": "82E4e60e73db2e06A00a079788F7d71f75b61a4b75f28c4c9427036d6"},
                {"type": "md5", "value": "7Ac236b1a82dac89e7cf45d2b48"},
            ],
            unencrypted_checksums=[
                {"type": "sha256", "value": "82E4e60e73db2e06A00a079788F7d71f75b61a4b75f28c4c9427036d6"},
                {"type": "md5", "value": "7Ac236b1a82dac89e7cf45d2b48"},
            ],
        )
        self.user_id = "current"
        self.user_generated_id = "5fb82fa1dcf9431fa5fcfb72e2d2ee14"
        self.test_user = {
            "userId": self.user_generated_id,
            "name": "tester",
        }
        class_dbservice = "metadata_backend.api.operators.object_base.DBService"
        self.patch_object_dbservice = patch(class_dbservice, spec=True)
        self.MockedObjectDbService = self.patch_object_dbservice.start()
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
        self.patch_user = patch(
            "metadata_backend.api.operators.user.UserOperator._generate_accession_id",
            return_value=self.user_generated_id,
            autospec=True,
        )
        self.patch_user.start()
        self.patch_project = patch(
            "metadata_backend.api.operators.project.ProjectOperator._generate_accession_id",
            return_value=self.project_generated_id,
            autospec=True,
        )
        self.patch_project.start()
        self.patch_file = patch(
            "metadata_backend.api.operators.file.FileOperator._generate_accession_id",
            return_value=self.file_id,
            autospec=True,
        )
        self.patch_file.start()

        self.session_return = aiohttp_session.Session(
            "test-identity",
            new=True,
            data={},
        )

        self.session_return["access_token"] = "not-really-a-token"  # nosec
        self.session_return["at"] = time.time()
        self.session_return["user_info"] = "value"
        self.session_return["oidc_state"] = "state"

        self.aiohttp_session_get_session_mock = AsyncMock()
        self.aiohttp_session_get_session_mock.return_value = self.session_return
        self.p_get_sess_restapi = patch(
            "metadata_backend.api.handlers.restapi.aiohttp_session.get_session",
            self.aiohttp_session_get_session_mock,
        )

    def tearDown(self):
        """Stop patchers."""
        self.patch_object_dbservice.stop()
        self.patch_dbservice.stop()
        self.patch_accession.stop()
        self.patch_submission.stop()
        self.patch_user.stop()
        self.patch_project.stop()
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
        with patch(
            ("metadata_backend.api.operators.object.ObjectOperator._format_data_to_create_and_add_to_db"),
            return_value={"accessionId": self.accession_id},
        ):
            with patch("metadata_backend.api.operators.object_xml.XMLToJSONParser"):
                data = await operator.create_metadata_object("study", "<MOCK_ELEM></MOCK_ELEM>")
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
                m_date.utcnow.return_value = datetime.datetime(2020, 4, 14)
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

    async def test_wrong_data_is_set_to_json_when_replacing(self):
        """Test operator replace catches error."""
        operator = ObjectOperator(self.client)
        with patch(
            "metadata_backend.api.operators.object.ObjectOperator._replace_object_from_db",
            return_value=self.accession_id,
        ):
            with patch("metadata_backend.api.operators.object.datetime") as m_date:
                m_date.utcnow.return_value = datetime.datetime(2020, 4, 14)
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

    async def test_correct_data_is_set_to_json_when_replacing(self):
        """Test operator replaces object and adds necessary info."""
        operator = ObjectOperator(self.client)
        with patch(
            "metadata_backend.api.operators.object.ObjectOperator._replace_object_from_db",
            return_value=self.accession_id,
        ) as mocked_insert:
            with patch("metadata_backend.api.operators.object.datetime") as m_date:
                m_date.utcnow.return_value = datetime.datetime(2020, 4, 14)
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

    async def test_correct_data_is_set_to_json_when_updating(self):
        """Test operator updates object and adds necessary info."""
        operator = ObjectOperator(self.client)
        with patch(
            ("metadata_backend.api.operators.object.ObjectOperator._update_object_from_db"),
            return_value=self.accession_id,
        ) as mocked_insert:
            with patch("metadata_backend.api.operators.object.datetime") as m_date:
                m_date.utcnow.return_value = datetime.datetime(2020, 4, 14)
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
                m_date.utcnow.return_value = datetime.datetime(2020, 4, 14)
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
                with patch("metadata_backend.api.operators.object_xml.XMLToJSONParser"):
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
                with patch("metadata_backend.api.operators.object_xml.XMLToJSONParser"):
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

    async def test_working_query_params_are_passed_to_db_query(self):
        """Test that database is called with correct query."""
        operator = ObjectOperator(self.client)
        study_test = [
            {
                "publishDate": datetime.datetime(2020, 6, 14, 0, 0),
                "accessionId": "EDAG3945644754983408",
                "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
                "dateModified": datetime.datetime(2020, 6, 14, 0, 0),
            }
        ]
        study_total = [{"total": 0}]
        operator.db_service.do_aggregate.side_effect = [study_test, study_total]
        operator.db_service.do_aggregate = AsyncMock(side_effect=[study_test, study_total])
        query = MultiDictProxy(MultiDict([("studyAttributes", "foo")]))
        await operator.query_metadata_database("study", query, 1, 10, [])
        calls = [
            call(
                "study",
                [
                    {
                        "$match": {
                            "$or": [
                                {"studyAttributes.tag": re.compile(".*foo.*", re.IGNORECASE)},
                                {"studyAttributes.value": re.compile(".*foo.*", re.IGNORECASE)},
                            ]
                        }
                    },
                    {"$redact": {"$cond": {"if": {}, "then": "$$DESCEND", "else": "$$PRUNE"}}},
                    {"$skip": 0},
                    {"$limit": 10},
                    {"$project": {"_id": 0}},
                ],
            ),
            call(
                "study",
                [
                    {
                        "$match": {
                            "$or": [
                                {"studyAttributes.tag": re.compile(".*foo.*", re.IGNORECASE)},
                                {"studyAttributes.value": re.compile(".*foo.*", re.IGNORECASE)},
                            ]
                        }
                    },
                    {"$redact": {"$cond": {"if": {}, "then": "$$DESCEND", "else": "$$PRUNE"}}},
                    {"$count": "total"},
                ],
            ),
        ]
        operator.db_service.do_aggregate.assert_has_calls(calls, any_order=True)

    async def test_non_working_query_params_are_not_passed_to_db_query(self):
        """Test that database with empty query, when url params are wrong."""
        operator = ObjectOperator(self.client)
        study_test = [
            {
                "publishDate": datetime.datetime(2020, 6, 14, 0, 0),
                "accessionId": "EDAG3945644754983408",
                "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
                "dateModified": datetime.datetime(2020, 6, 14, 0, 0),
            }
        ]
        study_total = [{"total": 0}]
        operator.db_service.do_aggregate = AsyncMock(side_effect=[study_test, study_total])
        query = MultiDictProxy(MultiDict([("swag", "littinen")]))
        with patch(
            "metadata_backend.api.operators.object.ObjectOperator._format_read_data",
            return_value=study_test,
        ):
            await operator.query_metadata_database("study", query, 1, 10, [])
        calls = [
            call(
                "study",
                [
                    {"$match": {}},
                    {"$redact": {"$cond": {"if": {}, "then": "$$DESCEND", "else": "$$PRUNE"}}},
                    {"$skip": 0},
                    {"$limit": 10},
                    {"$project": {"_id": 0}},
                ],
            ),
            call(
                "study",
                [
                    {"$match": {}},
                    {"$redact": {"$cond": {"if": {}, "then": "$$DESCEND", "else": "$$PRUNE"}}},
                    {"$count": "total"},
                ],
            ),
        ]
        operator.db_service.do_aggregate.assert_has_calls(calls, any_order=True)
        self.assertEqual(operator.db_service.do_aggregate.call_count, 2)

    async def test_query_result_is_parsed_correctly(self):
        """Test JSON is read and correct pagination values are returned."""
        operator = ObjectOperator(self.client)
        multiple_result = [
            {
                "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
                "dateModified": datetime.datetime(2020, 6, 14, 0, 0),
                "accessionId": "EGA123456",
                "foo": "bar",
                "total": 100,
            },
            {
                "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
                "dateModified": datetime.datetime(2020, 6, 14, 0, 0),
                "accessionId": "EGA123456",
                "foo": "bar",
                "total": 100,
            },
        ]
        study_total = [{"total": 100}]
        operator.db_service.do_aggregate = AsyncMock(side_effect=[multiple_result, study_total])
        query = MultiDictProxy(MultiDict([]))
        (
            parsed,
            page_num,
            page_size,
            total_objects,
        ) = await operator.query_metadata_database("sample", query, 1, 10, [])
        for doc in parsed:
            self.assertEqual(doc["dateCreated"], "2020-06-14T00:00:00")
            self.assertEqual(doc["dateModified"], "2020-06-14T00:00:00")
            self.assertEqual(doc["accessionId"], "EGA123456")
        self.assertEqual(page_num, 1)
        self.assertEqual(page_size, 2)
        self.assertEqual(total_objects, 100)

    async def test_non_empty_query_result_raises_notfound(self):
        """Test that 404 is raised with empty query result."""
        operator = ObjectOperator(self.client)
        operator.db_service.do_aggregate = AsyncMock(return_value=None)
        query = MultiDictProxy(MultiDict([]))
        with patch(
            "metadata_backend.api.operators.object.ObjectOperator._format_read_data",
            return_value=[],
        ):
            with self.assertRaises(HTTPNotFound):
                await operator.query_metadata_database("study", query, 1, 10, [])

    async def test_query_skip_and_limit_are_set_correctly(self):
        """Test custom skip and limits."""
        operator = ObjectOperator(self.client)
        data = {"foo": "bar"}
        result = []
        operator.db_service.do_aggregate = AsyncMock(side_effect=[result, [{"total": 0}]])
        with patch(
            "metadata_backend.api.operators.object.ObjectOperator._format_read_data",
            return_value=data,
        ):
            await operator.query_metadata_database("sample", {}, 3, 50, [])
            calls = [
                call(
                    "sample",
                    [
                        {"$match": {}},
                        {"$redact": {"$cond": {"if": {}, "then": "$$DESCEND", "else": "$$PRUNE"}}},
                        {"$skip": 50 * (3 - 1)},
                        {"$limit": 50},
                        {"$project": {"_id": 0}},
                    ],
                ),
                call(
                    "sample",
                    [
                        {"$match": {}},
                        {"$redact": {"$cond": {"if": {}, "then": "$$DESCEND", "else": "$$PRUNE"}}},
                        {"$count": "total"},
                    ],
                ),
            ]
            operator.db_service.do_aggregate.assert_has_calls(calls, any_order=True)
            self.assertEqual(operator.db_service.do_aggregate.call_count, 2)

    async def test_get_object_project_connfail(self):
        """Test get object project, db connection failure."""
        operator = ObjectOperator(self.client)
        operator.db_service.query.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.get_object_project("template", self.accession_id)

    async def test_get_object_project_opfail(self):
        """Test get object project, db operation failure."""
        operator = ObjectOperator(self.client)
        operator.db_service.query.side_effect = OperationFailure("err")
        with self.assertRaises(HTTPBadRequest):
            await operator.get_object_project("template", self.accession_id)

    async def test_get_object_project_passes(self):
        """Test get object project returns project id."""
        operator = ObjectOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([self.test_submission])
        result = await operator.get_object_project("template", self.accession_id)
        operator.db_service.query.assert_called_once_with("template", {"accessionId": self.accession_id})
        self.assertEqual(result, self.project_generated_id)

    async def test_get_object_project_fails(self):
        """Test get object project returns nothing and raises an error."""
        operator = ObjectOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([])
        with self.assertRaises(HTTPBadRequest):
            await operator.get_object_project("template", self.accession_id)

    async def test_get_object_project_fails_missing_project(self):
        """Test get object project returns faulty object record that is missing project id."""
        operator = ObjectOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([self.test_submission_no_project])
        with self.assertRaises(HTTPBadRequest):
            await operator.get_object_project("template", self.accession_id)

    async def test_get_object_project_fails_invalid_collection(self):
        """Test get object project raises bad request on invalid collection."""
        operator = ObjectOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([])
        with self.assertRaises(HTTPBadRequest):
            await operator.get_object_project("something", self.accession_id)

    async def test_get_submission_project_connfail(self):
        """Test get submission project, db connection failure."""
        operator = SubmissionOperator(self.client)
        operator.db_service.query.side_effect = ConnectionFailure
        with self.assertRaises(HTTPInternalServerError):
            await operator.get_submission_project(self.submission_id)

    async def test_get_submission_project_opfail(self):
        """Test get submission project, db operation failure."""
        operator = SubmissionOperator(self.client)
        operator.db_service.query.side_effect = OperationFailure("err")
        with self.assertRaises(HTTPInternalServerError):
            await operator.get_submission_project(self.submission_id)

    async def test_get_submission_project_passes(self):
        """Test get submission project returns project id."""
        operator = SubmissionOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([self.test_submission])
        result = await operator.get_submission_project(self.submission_id)
        operator.db_service.query.assert_called_once_with(
            "submission", {"submissionId": self.submission_id}, {"_id": False, "projectId": 1}, limit=1
        )
        self.assertEqual(result, self.project_generated_id)

    async def test_get_submission_project_fails(self):
        """Test get submission project returns nothing and raises an error."""
        operator = SubmissionOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([])
        with self.assertRaises(HTTPBadRequest):
            await operator.get_submission_project(self.submission_id)

    async def test_get_submission_project_fails_missing_project(self):
        """Test get submission project returns faulty submission record that is missing project id."""
        operator = SubmissionOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([self.test_submission_no_project])
        with self.assertRaises(HTTPBadRequest):
            await operator.get_submission_project(self.submission_id)

    async def test_get_submission_project_fails_invalid_collection(self):
        """Test get submission project raises bad request on invalid collection."""
        operator = SubmissionOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([])
        with self.assertRaises(HTTPBadRequest):
            await operator.get_submission_project(self.submission_id)

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

    async def test_create_user_works_and_returns_userId(self):
        """Test create method for users work."""
        operator = UserOperator(self.client)
        data = {"user_id": "externalId", "real_name": "name", "projects": ""}
        operator.db_service.exists_user_by_external_id.return_value = None
        operator.db_service.create.return_value = True
        user = await operator.create_user(data)
        operator.db_service.create.assert_called_once()
        self.assertEqual(user, self.user_generated_id)

    async def test_create_user_on_create_fails(self):
        """Test create method fails on db create."""
        operator = UserOperator(self.client)
        data = {"user_id": "externalId", "real_name": "name", "projects": ""}
        operator.db_service.exists_user_by_external_id.return_value = None
        operator.db_service.create.return_value = False
        with self.assertRaises(HTTPBadRequest):
            await operator.create_user(data)
            operator.db_service.create.assert_called_once()

    async def test_check_user_doc_fails(self):
        """Test check user doc fails."""
        request = Mock_Request()
        db_client = MagicMock()
        db_database = MagicMock()
        db_collection = AsyncMock()
        db_client.__getitem__.return_value = db_database
        db_database.__getitem__.return_value = db_collection

        request.app["db_client"] = db_client
        with self.p_get_sess_restapi:
            operator = UserOperator(self.client)
            with self.assertRaises(HTTPBadRequest):
                await operator.check_user_has_doc(request, "something", self.user_generated_id, self.submission_id)

    async def test_check_user_doc_passes(self):
        """Test check user doc passes when object has same project id and user."""
        UserOperator.check_user_has_doc = make_mocked_coro(True)
        request = Mock_Request()
        db_client = MagicMock()
        db_database = MagicMock()
        db_collection = AsyncMock()
        db_client.__getitem__.return_value = db_database
        db_database.__getitem__.return_value = db_collection

        request.app["db_client"] = db_client
        operator = UserOperator(self.client)
        with patch(
            "metadata_backend.api.operators.submission.SubmissionOperator.get_submission_project",
            return_value=self.project_generated_id,
        ):
            with self.p_get_sess_restapi:
                with patch(
                    "metadata_backend.api.operators.user.UserOperator.read_user",
                    return_value={"userId": "test"},
                ):
                    with patch(
                        "metadata_backend.api.operators.user.UserOperator.check_user_has_project",
                        return_value=True,
                    ):
                        result = await operator.check_user_has_doc(
                            request, "submissions", self.user_generated_id, self.submission_id
                        )
                        self.assertTrue(result)

    async def test_create_user_works_existing_userId(self):
        """Test create method for existing user."""
        operator = UserOperator(self.client)
        data = {"user_id": "eppn", "real_name": "name", "projects": ""}
        operator.db_service.exists_user_by_external_id.return_value = self.user_generated_id
        user = await operator.create_user(data)
        operator.db_service.create.assert_not_called()
        self.assertEqual(user, self.user_generated_id)

    async def test_create_user_fails(self):
        """Test create user fails."""
        data = {"user_id": "eppn", "real_name": "name", "projects": ""}
        operator = UserOperator(self.client)
        operator.db_service.exists_user_by_external_id.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.create_user(data)

    async def test_reading_user_works(self):
        """Test user object is read from db correctly."""
        operator = UserOperator(self.client)
        operator.db_service.exists.return_value = True
        operator.db_service.read.return_value = self.test_user
        read_data = await operator.read_user(self.user_id)
        operator.db_service.exists.assert_called_once()
        operator.db_service.read.assert_called_once_with("user", self.user_id)
        self.assertEqual(read_data, self.test_user)

    async def test_read_user_fails(self):
        """Test user read fails."""
        operator = UserOperator(self.client)
        operator.db_service.exists.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.read_user(self.user_id)

    async def test_check_user_exists_passes(self):
        """Test user exists passes."""
        operator = UserOperator(self.client)
        operator.db_service.exists = AsyncMock(return_value=True)
        await operator._check_user_exists(self.user_id)
        operator.db_service.exists.assert_called_once()

    async def test_check_user_exists_fails(self):
        """Test user exists fails."""
        operator = UserOperator(self.client)
        operator.db_service.exists = AsyncMock(return_value=False)
        with self.assertRaises(HTTPNotFound):
            await operator._check_user_exists(self.user_id)
            operator.db_service.exists.assert_called_once()

    async def test_user_update_passes_and_returns_id(self):
        """Test update method for users works."""
        patch = [{"op": "add", "path": "/name", "value": "test2"}]
        operator = UserOperator(self.client)
        operator.db_service.exists.return_value = True
        operator.db_service.patch.return_value = True
        user = await operator.update_user(self.test_user, patch)
        operator.db_service.exists.assert_called_once()
        operator.db_service.patch.assert_called_once()
        self.assertEqual(user["userId"], self.user_generated_id)

    async def test_user_update_fails_with_bad_patch(self):
        """Test user update raises error with improper JSON Patch."""
        patch = [{"op": "replace", "path": "/nothing"}]
        operator = UserOperator(self.client)
        operator.db_service.exists.return_value = True
        operator.db_service.patch.return_value = False
        with self.assertRaises(HTTPBadRequest):
            await operator.update_user(self.test_user, patch)
            operator.db_service.exists.assert_called_once()

    async def test_update_user_fails(self):
        """Test user update fails."""
        operator = UserOperator(self.client)
        operator.db_service.exists.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.update_user(self.user_id, [])

    async def test_deleting_user_passes(self):
        """Test user is deleted correctly."""
        operator = UserOperator(self.client)
        operator.db_service.exists.return_value = True
        operator.db_service.delete.return_value = True
        await operator.delete_user(self.user_id)
        operator.db_service.delete.assert_called_with("user", "current")

    async def test_deleting_user_fails_on_delete(self):
        """Test user fails on delete operation."""
        operator = UserOperator(self.client)
        operator.db_service.exists.return_value = True
        operator.db_service.delete.return_value = False
        with self.assertRaises(HTTPBadRequest):
            await operator.delete_user(self.user_id)
            operator.db_service.delete.assert_called_with("user", "current")

    async def test_deleting_user_fails(self):
        """Test user delete fails."""
        operator = UserOperator(self.client)
        operator.db_service.exists.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.delete_user(self.user_id)

    async def test_check_user_has_project_passes(self):
        """Test check user has project and doesn't raise an exception."""
        operator = UserOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator(["1"])
        result = await operator.check_user_has_project(self.project_generated_id, self.user_generated_id)
        operator.db_service.query.assert_called_once_with(
            "user",
            {"projects": {"$elemMatch": {"projectId": self.project_generated_id}}, "userId": self.user_generated_id},
        )
        self.assertTrue(result)

    async def test_check_user_has_no_project(self):
        """Test check user does not have project and raises unauthorised."""
        operator = UserOperator(self.client)
        self.MockedDbService().query.return_value = AsyncIterator([])
        result = await operator.check_user_has_project(self.project_generated_id, self.user_generated_id)
        operator.db_service.query.assert_called_once_with(
            "user",
            {"projects": {"$elemMatch": {"projectId": self.project_generated_id}}, "userId": self.user_generated_id},
        )
        self.assertFalse(result)

    async def test_check_user_has_project_connfail(self):
        """Test check user has project, db connection failure."""
        operator = UserOperator(self.client)
        operator.db_service.query.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.check_user_has_project(self.project_generated_id, self.user_generated_id)

    async def test_check_user_has_project_opfail(self):
        """Test check user has project, db operation failure."""
        operator = UserOperator(self.client)
        operator.db_service.query.side_effect = OperationFailure("err")
        with self.assertRaises(HTTPBadRequest):
            await operator.check_user_has_project(self.project_generated_id, self.user_generated_id)

    async def test_get_signing_key_found(self):
        """Test existing key can be read with user id."""
        operator = UserOperator(self.client)
        operator.db_service.exists.return_value = True
        operator.db_service.read_by_key_value.return_value = {"signingKey": "testkey"}
        read_signing_key = await operator.get_signing_key(self.user_id)
        operator.db_service.exists.assert_called_once()
        operator.db_service.read_by_key_value.assert_called_once_with(
            "user",
            {
                "userId": self.user_id,
            },
            {
                "_id": 0,
                "signingKey": 1,
            },
        )
        self.assertEqual(read_signing_key, "testkey")

    async def test_get_signing_key_not_found(self):
        """Test that we get None when user has no key."""
        operator = UserOperator(self.client)
        operator.db_service.exists.return_value = True
        operator.db_service.read_by_key_value.return_value = {}
        read_signing_key = await operator.get_signing_key(self.user_id)
        operator.db_service.exists.assert_called_once()
        operator.db_service.read_by_key_value.assert_called_once_with(
            "user",
            {
                "userId": self.user_id,
            },
            {
                "_id": 0,
                "signingKey": 1,
            },
        )
        self.assertIsNone(read_signing_key)

    async def test_create_project_works_and_returns_projectId(self):
        """Test create method for projects work."""
        operator = ProjectOperator(self.client)
        operator.db_service.exists_project_by_external_id = AsyncMock(return_value=None)
        operator.db_service.create = AsyncMock(return_value=True)
        project = await operator.create_project(self.project_id)
        operator.db_service.create.assert_called_once()
        self.assertEqual(project, self.project_generated_id)

    async def test_create_project_works_existing_projectId(self):
        """Test create method for existing user."""
        operator = ProjectOperator(self.client)
        operator.db_service.exists_project_by_external_id = AsyncMock(return_value=self.project_generated_id)
        project = await operator.create_project(self.project_id)
        operator.db_service.create.assert_not_called()
        self.assertEqual(project, self.project_generated_id)

    async def test_create_project_on_create_fails(self):
        """Test create method fails on db create."""
        operator = ProjectOperator(self.client)
        operator.db_service.exists_project_by_external_id = AsyncMock(return_value=None)
        operator.db_service.create = AsyncMock(return_value=False)
        with self.assertRaises(HTTPBadRequest):
            await operator.create_project(self.project_id)
            operator.db_service.create.assert_called_once()

    async def test_create_project_fails(self):
        """Test create project fails."""
        operator = ProjectOperator(self.client)
        self.MockedDbService().exists_project_by_external_id.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.create_project(self.project_id)

    async def test_check_project_exists_fails(self):
        """Test project exists fails."""
        operator = ProjectOperator(self.client)
        operator.db_service.exists = AsyncMock(return_value=False)
        with self.assertRaises(HTTPNotFound):
            await operator.check_project_exists(self.project_id)
            operator.db_service.exists.assert_called_once()

    async def test_check_project_exists_passes(self):
        """Test project exists passes."""
        operator = ProjectOperator(self.client)
        operator.db_service.exists = AsyncMock(return_value=True)
        await operator.check_project_exists(self.project_id)
        operator.db_service.exists.assert_called_once()

    async def test_project_objects_remove_passes(self):
        """Test remove objects method for projects works."""
        operator = ProjectOperator(self.client)
        operator.db_service.exists = AsyncMock(return_value=True)
        operator.db_service.remove = AsyncMock(return_value=None)
        await operator.remove_templates(self.project_generated_id, ["id"])
        operator.db_service.exists.assert_called_once()
        operator.db_service.remove.assert_called_once()
        self.assertEqual(len(operator.db_service.remove.mock_calls), 1)

    async def test_project_objects_remove_fails(self):
        """Test remove objects method for projects fails."""
        operator = ProjectOperator(self.client)
        operator.db_service.exists = AsyncMock(return_value=True)
        operator.db_service.remove.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.remove_templates(self.project_generated_id, ["id"])

    async def test_project_objects_append_passes(self):
        """Test append objects method for projects works."""
        operator = ProjectOperator(self.client)
        operator.db_service.exists = AsyncMock(return_value=True)
        operator.db_service.append = AsyncMock(return_value=True)
        await operator.assign_templates(self.project_generated_id, [])
        operator.db_service.exists.assert_called_once()
        operator.db_service.append.assert_called_once()
        self.assertEqual(len(operator.db_service.append.mock_calls), 1)

    async def test_project_objects_append_on_result_fails(self):
        """Test append objects method for projects fails on db response validation."""
        operator = ProjectOperator(self.client)
        operator.db_service.exists = AsyncMock(return_value=True)
        operator.db_service.append = AsyncMock(return_value=False)
        with self.assertRaises(HTTPBadRequest):
            await operator.assign_templates(self.project_generated_id, [])
            operator.db_service.exists.assert_called_once()
            operator.db_service.append.assert_called_once()

    async def test_project_objects_assing_fails(self):
        """Test append objects method for projects fails."""
        operator = ProjectOperator(self.client)
        operator.db_service.exists.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.assign_templates(self.project_generated_id, [])

    async def test_update_project_fail_no_project(self):
        """Test that project which does not exist can not be updated."""
        operator = ProjectOperator(self.client)
        with self.assertRaises(HTTPNotFound):
            with patch(
                "metadata_backend.api.operators.project.ProjectOperator.check_project_exists",
                side_effect=HTTPNotFound,
            ):
                await operator.update_project(self.project_generated_id, [])

    async def test_update_project_fail_connfail(self):
        """Test project update failure with database connection failure."""
        operator = ProjectOperator(self.client)
        operator.db_service.patch.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            with patch(
                "metadata_backend.api.operators.project.ProjectOperator.check_project_exists", return_value=True
            ):
                await operator.update_project(self.project_generated_id, [])

    async def test_update_project_fail_general(self):
        """Test project update failure with general error."""
        operator = ProjectOperator(self.client)
        operator.db_service.patch = AsyncMock(return_value=False)
        with self.assertRaises(HTTPBadRequest):
            with patch(
                "metadata_backend.api.operators.project.ProjectOperator.check_project_exists", return_value=True
            ):
                await operator.update_project(self.project_generated_id, [])

    async def test_update_project_pass(self):
        """Test project update passes."""
        operator = ProjectOperator(self.client)
        operator.db_service.patch = AsyncMock(return_value=True)
        with patch("metadata_backend.api.operators.project.ProjectOperator.check_project_exists", return_value=True):
            pid = await operator.update_project(self.project_generated_id, [])
            self.assertEqual(pid, self.project_generated_id)

    async def test_create_file_pass(self):
        """Test create file passes."""
        operator = FileOperator(self.client)

        operator.db_service.read_by_key_value = AsyncMock(return_value=None)
        operator.db_service.create = AsyncMock(return_value=True)

        file_id, version = await operator.create_file_or_version(self.test_file)
        self.assertEqual(file_id, self.file_id)
        self.assertEqual(version, 1)

    async def test_create_file_version_pass(self):
        """Test create file version passes."""
        operator = FileOperator(self.client)

        file_in_db = {
            "accessionId": self.file_id,
            "currentVersion": {
                "version": 2,
                "date": "iso-date",
                "published": True,
                "bytes": 20,
                "submissions": ["s1"],
                "encrypted_checksums": [
                    {"type": "sha256", "value": "82E4e60e73db2e06A00a079788F7d71f75b61a4b75f28c4c9427036d6"},
                    {"type": "md5", "value": "7Ac236b1a82dac89e7cf45d2b48"},
                ],
                "unencrypted_checksums": [
                    {"type": "sha256", "value": "82E4e60e73db2e06A00a079788F7d71f75b61a4b75f28c4c9427036d6"},
                    {"type": "md5", "value": "7Ac236b1a82dac89e7cf45d2b48"},
                ],
            },
        }
        operator.db_service.read_by_key_value = AsyncMock(return_value=file_in_db)

        operator.db_service.append = AsyncMock(return_value=None)

        file_id, version = await operator.create_file_or_version(self.test_file)
        self.assertEqual(file_id, self.file_id)
        self.assertEqual(version, 3)


if __name__ == "__main__":
    unittest.main()
