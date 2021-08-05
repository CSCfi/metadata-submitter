"""Test api endpoints from views module."""
import datetime
import re
import unittest
from uuid import uuid4
from unittest.mock import MagicMock, patch, call

from aiohttp.web import HTTPBadRequest, HTTPNotFound, HTTPUnprocessableEntity
from unittest import IsolatedAsyncioTestCase

from multidict import MultiDict, MultiDictProxy
from pymongo.errors import ConnectionFailure

from metadata_backend.api.operators import (
    FolderOperator,
    Operator,
    XMLOperator,
    UserOperator,
)


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
        self.accession_id = uuid4().hex
        self.folder_id = uuid4().hex
        self.test_folder = {
            "folderId": self.folder_id,
            "name": "Mock folder",
            "description": "test mock folder",
            "published": False,
            "metadataObjects": [{"accessionId": "EGA1234567", "schema": "study"}],
        }
        self.user_id = "current"
        self.user_generated_id = "5fb82fa1dcf9431fa5fcfb72e2d2ee14"
        self.test_user = {
            "userId": self.user_generated_id,
            "name": "tester",
            "drafts": [],
            "folders": [],
        }
        class_dbservice = "metadata_backend.api.operators.DBService"
        self.patch_dbservice = patch(class_dbservice, spec=True)
        self.MockedDbService = self.patch_dbservice.start()
        self.patch_accession = patch(
            "metadata_backend.api.operators.Operator._generate_accession_id",
            return_value=self.accession_id,
            autospec=True,
        )
        self.patch_accession.start()
        self.patch_folder = patch(
            ("metadata_backend.api.operators.FolderOperator._generate_folder_id"),
            return_value=self.folder_id,
            autospec=True,
        )
        self.patch_folder.start()
        self.patch_user = patch(
            ("metadata_backend.api.operators.UserOperator._generate_user_id"),
            return_value=self.user_generated_id,
            autospec=True,
        )
        self.patch_user.start()

    def tearDown(self):
        """Stop patchers."""
        self.patch_dbservice.stop()
        self.patch_accession.stop()
        self.patch_folder.stop()
        self.patch_user.stop()

    async def test_reading_metadata_works(self):
        """Test JSON is read from db correctly."""
        operator = Operator(self.client)
        data = {
            "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
            "dateModified": datetime.datetime(2020, 6, 14, 0, 0),
            "accessionId": "EGA123456",
            "foo": "bar",
        }
        operator.db_service.read.return_value = data
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
        operator = XMLOperator(self.client)
        data = {"accessionId": "EGA123456", "content": "<MOCK_ELEM></MOCK_ELEM>"}
        operator.db_service.read.return_value = data
        r_data, c_type = await operator.read_metadata_object("sample", "EGA123456")
        operator.db_service.read.assert_called_once_with("sample", "EGA123456")
        self.assertEqual(c_type, "text/xml")
        self.assertEqual(r_data, data["content"])

    async def test_reading_with_non_valid_id_raises_error(self):
        """Test read metadata HTTPNotFound is raised."""
        operator = Operator(self.client)
        operator.db_service.read.return_value = False
        with self.assertRaises(HTTPNotFound):
            await operator.read_metadata_object("study", "EGA123456")

    async def test_db_error_raises_400_error(self):
        """Test read metadata HTTPBadRequest is raised."""
        operator = Operator(self.client)
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
        result = Operator(self.client)._format_single_dict("study", study_test)
        self.assertEqual(result["publishDate"], "2020-06-14T00:00:00")
        self.assertEqual(result["dateCreated"], "2020-06-14T00:00:00")
        self.assertEqual(result["dateModified"], "2020-06-14T00:00:00")
        with self.assertRaises(KeyError):
            result["_Id"]

    async def test_json_create_passes_and_returns_accessionId(self):
        """Test create method for JSON works."""
        operator = Operator(self.client)
        data = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {"studyTitle": "Highly", "studyType": "Other"},
        }
        operator.db_service.create.return_value = True
        accession = await operator.create_metadata_object("study", data)
        operator.db_service.create.assert_called_once()
        self.assertEqual(accession, self.accession_id)

    async def test_json_replace_passes_and_returns_accessionId(self):
        """Test replace method for JSON works."""
        data = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {"studyTitle": "Highly", "studyType": "Other"},
        }
        operator = Operator(self.client)
        operator.db_service.exists.return_value = True
        operator.db_service.replace.return_value = True
        accession = await operator.replace_metadata_object("study", self.accession_id, data)
        operator.db_service.replace.assert_called_once()
        self.assertEqual(accession, self.accession_id)

    async def test_json_replace_raises_if_not_exists(self):
        """Test replace method raises error."""
        operator = Operator(self.client)
        operator.db_service.exists.return_value = False
        operator.db_service.replace.return_value = True
        with self.assertRaises(HTTPNotFound):
            await operator.replace_metadata_object("study", self.accession_id, {})
            operator.db_service.replace.assert_called_once()

    async def test_db_error_replace_raises_400_error(self):
        """Test replace metadata HTTPBadRequest is raised."""
        operator = Operator(self.client)
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
        operator = Operator(self.client)
        operator.db_service.read.return_value = db_data
        operator.db_service.exists.return_value = True
        operator.db_service.update.return_value = True
        accession = await operator.update_metadata_object("study", self.accession_id, data)
        operator.db_service.update.assert_called_once()
        self.assertEqual(accession, self.accession_id)

    async def test_json_update_raises_if_not_exists(self):
        """Test update method raises error."""
        operator = Operator(self.client)
        operator.db_service.exists.return_value = False
        operator.db_service.replace.return_value = True
        with self.assertRaises(HTTPNotFound):
            await operator.update_metadata_object("study", self.accession_id, {})
            operator.db_service.update.assert_called_once()

    async def test_db_error_update_raises_400_error(self):
        """Test update metadata HTTPBadRequest is raised."""
        operator = Operator(self.client)
        operator.db_service.exists.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.update_metadata_object("study", self.accession_id, {})

    async def test_xml_create_passes_and_returns_accessionId(self):
        """Test create method for XML works. Patch JSON related calls."""
        operator = XMLOperator(self.client)
        operator.db_service.db_client = self.client
        operator.db_service.create.return_value = True
        with patch(
            ("metadata_backend.api.operators.Operator._format_data_to_create_and_add_to_db"),
            return_value=self.accession_id,
        ):
            with patch("metadata_backend.api.operators.XMLToJSONParser"):
                accession = await operator.create_metadata_object("study", "<MOCK_ELEM></MOCK_ELEM>")
        operator.db_service.create.assert_called_once()
        self.assertEqual(accession, self.accession_id)

    async def test_correct_data_is_set_to_json_when_creating(self):
        """Test operator creates object and adds necessary info."""
        operator = Operator(self.client)
        with patch(
            ("metadata_backend.api.operators.Operator._insert_formatted_object_to_db"),
            return_value=self.accession_id,
        ) as mocked_insert:
            with patch("metadata_backend.api.operators.datetime") as m_date:
                m_date.utcnow.return_value = datetime.datetime(2020, 4, 14)
                acc = await (operator._format_data_to_create_and_add_to_db("study", {}))
                mocked_insert.assert_called_once_with(
                    "study",
                    {
                        "accessionId": self.accession_id,
                        "dateCreated": datetime.datetime(2020, 4, 14),
                        "dateModified": datetime.datetime(2020, 4, 14),
                        "publishDate": datetime.datetime(2020, 6, 14),
                    },
                )
            self.assertEqual(acc, self.accession_id)

    async def test_wront_data_is_set_to_json_when_replacing(self):
        """Test operator replace catches error."""
        operator = Operator(self.client)
        with patch("metadata_backend.api.operators.Operator._replace_object_from_db", return_value=self.accession_id):
            with patch("metadata_backend.api.operators.datetime") as m_date:
                m_date.utcnow.return_value = datetime.datetime(2020, 4, 14)
                with self.assertRaises(HTTPBadRequest):
                    await (
                        operator._format_data_to_replace_and_add_to_db(
                            "study",
                            self.accession_id,
                            {
                                "accessionId": self.accession_id,
                                "dateCreated": datetime.datetime(2020, 4, 14),
                                "dateModified": datetime.datetime(2020, 4, 14),
                                "publishDate": datetime.datetime(2020, 6, 14),
                            },
                        )
                    )

    async def test_correct_data_is_set_to_json_when_replacing(self):
        """Test operator replaces object and adds necessary info."""
        operator = Operator(self.client)
        with patch(
            "metadata_backend.api.operators.Operator._replace_object_from_db", return_value=self.accession_id
        ) as mocked_insert:
            with patch("metadata_backend.api.operators.datetime") as m_date:
                m_date.utcnow.return_value = datetime.datetime(2020, 4, 14)
                acc = await (operator._format_data_to_replace_and_add_to_db("study", self.accession_id, {}))
                mocked_insert.assert_called_once_with(
                    "study",
                    self.accession_id,
                    {"accessionId": self.accession_id, "dateModified": datetime.datetime(2020, 4, 14)},
                )
            self.assertEqual(acc, self.accession_id)

    async def test_correct_data_is_set_to_json_when_updating(self):
        """Test operator updates object and adds necessary info."""
        operator = Operator(self.client)
        with patch(
            ("metadata_backend.api.operators.Operator._update_object_from_db"),
            return_value=self.accession_id,
        ) as mocked_insert:
            with patch("metadata_backend.api.operators.datetime") as m_date:
                m_date.utcnow.return_value = datetime.datetime(2020, 4, 14)
                acc = await (operator._format_data_to_update_and_add_to_db("study", self.accession_id, {}))
                mocked_insert.assert_called_once_with(
                    "study",
                    self.accession_id,
                    {"accessionId": self.accession_id, "dateModified": datetime.datetime(2020, 4, 14)},
                )
            self.assertEqual(acc, self.accession_id)

    async def test_wrong_data_is_set_to_json_when_updating(self):
        """Test operator update catches error."""
        operator = Operator(self.client)
        with patch(
            ("metadata_backend.api.operators.Operator._update_object_from_db"),
            return_value=self.accession_id,
        ):
            with patch("metadata_backend.api.operators.datetime") as m_date:
                m_date.utcnow.return_value = datetime.datetime(2020, 4, 14)
                with self.assertRaises(HTTPBadRequest):
                    await (
                        operator._format_data_to_update_and_add_to_db(
                            "study",
                            self.accession_id,
                            {
                                "accessionId": self.accession_id,
                                "dateCreated": datetime.datetime(2020, 4, 14),
                                "dateModified": datetime.datetime(2020, 4, 14),
                                "publishDate": datetime.datetime(2020, 6, 14),
                            },
                        )
                    )

    async def test_correct_data_is_set_to_xml_when_creating(self):
        """Test XMLoperator creates object and adds necessary info."""
        operator = XMLOperator(self.client)
        operator.db_service.db_client = self.client
        xml_data = "<MOCK_ELEM></MOCK_ELEM>"
        with patch(
            ("metadata_backend.api.operators.Operator._format_data_to_create_and_add_to_db"),
            return_value=self.accession_id,
        ):
            with patch(
                ("metadata_backend.api.operators.XMLOperator._insert_formatted_object_to_db"),
                return_value=self.accession_id,
            ) as m_insert:
                with patch("metadata_backend.api.operators.XMLToJSONParser"):
                    acc = await (operator._format_data_to_create_and_add_to_db("study", xml_data))
                    m_insert.assert_called_once_with(
                        "xml-study", {"accessionId": self.accession_id, "content": xml_data}
                    )
                    self.assertEqual(acc, self.accession_id)

    async def test_correct_data_is_set_to_xml_when_replacing(self):
        """Test XMLoperator replaces object and adds necessary info."""
        operator = XMLOperator(self.client)
        operator.db_service.db_client = self.client
        xml_data = "<MOCK_ELEM></MOCK_ELEM>"
        with patch(
            "metadata_backend.api.operators.Operator._format_data_to_replace_and_add_to_db",
            return_value=self.accession_id,
        ):
            with patch(
                "metadata_backend.api.operators.XMLOperator._replace_object_from_db",
                return_value=self.accession_id,
            ) as m_insert:
                with patch("metadata_backend.api.operators.XMLToJSONParser"):
                    acc = await (operator._format_data_to_replace_and_add_to_db("study", self.accession_id, xml_data))
                    m_insert.assert_called_once_with(
                        "xml-study",
                        self.accession_id,
                        {"accessionId": self.accession_id, "content": xml_data},
                    )
                    self.assertEqual(acc, self.accession_id)

    async def test_deleting_metadata_deletes_json_and_xml(self):
        """Test metadata is deleted."""
        operator = Operator(self.client)
        operator.db_service.db_client = self.client
        operator.db_service.exists.return_value = True
        operator.db_service.delete.return_value = True
        await operator.delete_metadata_object("sample", "EGA123456")
        self.assertEqual(operator.db_service.delete.call_count, 2)
        operator.db_service.delete.assert_called_with("sample", "EGA123456")

    async def test_deleting_metadata_delete_raises(self):
        """Test error raised with delete."""
        operator = Operator(self.client)
        operator.db_service.db_client = self.client
        operator.db_service.exists.return_value = False
        operator.db_service.delete.return_value = True
        with self.assertRaises(HTTPNotFound):
            await operator.delete_metadata_object("sample", "EGA123456")
            self.assertEqual(operator.db_service.delete.call_count, 2)
            operator.db_service.delete.assert_called_with("sample", "EGA123456")

    async def test_deleting_metadata_delete_raises_bad_request(self):
        """Test bad request error raised with delete."""
        operator = Operator(self.client)
        operator.db_service.db_client = self.client
        operator.db_service.exists.return_value = True
        operator.db_service.delete.return_value = False
        with self.assertRaises(HTTPBadRequest):
            await operator.delete_metadata_object("sample", "EGA123456")
            self.assertEqual(operator.db_service.delete.call_count, 2)
            operator.db_service.delete.assert_called_with("sample", "EGA123456")

    async def test_working_query_params_are_passed_to_db_query(self):
        """Test that database is called with correct query."""
        operator = Operator(self.client)
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
        operator = Operator(self.client)
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
        query = MultiDictProxy(MultiDict([("swag", "littinen")]))
        with patch(
            "metadata_backend.api.operators.Operator._format_read_data",
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
        operator = Operator(self.client)
        multiple_result = [
            {
                "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
                "dateModified": datetime.datetime(2020, 6, 14, 0, 0),
                "accessionId": "EGA123456",
                "foo": "bar",
            },
            {
                "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
                "dateModified": datetime.datetime(2020, 6, 14, 0, 0),
                "accessionId": "EGA123456",
                "foo": "bar",
            },
        ]
        study_total = [{"total": 100}]
        operator.db_service.do_aggregate.side_effect = [multiple_result, study_total]
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
        operator = Operator(self.client)
        operator.db_service.query = MagicMock()
        query = MultiDictProxy(MultiDict([]))
        with patch(
            "metadata_backend.api.operators.Operator._format_read_data",
            return_value=[],
        ):
            with self.assertRaises(HTTPNotFound):
                await operator.query_metadata_database("study", query, 1, 10, [])

    async def test_query_skip_and_limit_are_set_correctly(self):
        """Test custom skip and limits."""
        operator = Operator(self.client)
        data = {"foo": "bar"}
        result = []
        operator.db_service.do_aggregate.side_effect = [result, [{"total": 0}]]
        with patch(
            "metadata_backend.api.operators.Operator._format_read_data",
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

    async def test_create_folder_works_and_returns_folderId(self):
        """Test create method for folders work."""
        operator = FolderOperator(self.client)
        data = {"name": "Mock folder", "description": "test mock folder"}
        operator.db_service.create.return_value = True
        folder = await operator.create_folder(data)
        operator.db_service.create.assert_called_once()
        self.assertEqual(folder, self.folder_id)

    async def test_create_folder_fails(self):
        """Test create method for folders fails."""
        operator = FolderOperator(self.client)
        data = {"name": "Mock folder", "description": "test mock folder"}
        operator.db_service.create.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.create_folder(data)

    async def test_create_folder_db_create_fails(self):
        """Test create method for folders db create fails."""
        operator = FolderOperator(self.client)
        data = {"name": "Mock folder", "description": "test mock folder"}
        operator.db_service.create.return_value = False
        with self.assertRaises(HTTPBadRequest):
            await operator.create_folder(data)

    async def test_query_folders_empty_list(self):
        """Test query returns empty list."""
        operator = FolderOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([])
        folders = await operator.query_folders({}, 1, 5)
        operator.db_service.query.assert_called_once()
        self.assertEqual(folders, ([], 0))

    async def test_query_folders_1_item(self):
        """Test query returns a list with item."""
        operator = FolderOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([{"name": "folder"}])
        folders = await operator.query_folders({}, 1, 5)
        operator.db_service.query.assert_called_once()
        self.assertEqual(folders, ([{"name": "folder"}], 1))

    async def test_check_object_folder_fails(self):
        """Test check object folder fails."""
        operator = FolderOperator(self.client)
        operator.db_service.query.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.check_object_in_folder("study", self.accession_id)

    async def test_check_object_folder_passes(self):
        """Test check object folder returns proper data."""
        operator = FolderOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([self.test_folder])
        result = await operator.check_object_in_folder("study", self.accession_id)
        operator.db_service.query.assert_called_once_with(
            "folder", {"metadataObjects": {"$elemMatch": {"accessionId": self.accession_id, "schema": "study"}}}
        )
        self.assertEqual(result, (True, self.folder_id, False))

    async def test_check_object_folder_multiple_objects_fails(self):
        """Test check object folder returns multiple unique folders."""
        operator = FolderOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([self.test_folder, self.test_folder])
        with self.assertRaises(HTTPUnprocessableEntity):
            await operator.check_object_in_folder("study", self.accession_id)
            operator.db_service.query.assert_called_once_with(
                "folder", {"metadataObjects": {"$elemMatch": {"accessionId": self.accession_id, "schema": "study"}}}
            )

    async def test_check_object_folder_no_data(self):
        """Test check object folder returns no data."""
        operator = FolderOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([])
        result = await operator.check_object_in_folder("study", self.accession_id)
        operator.db_service.query.assert_called_once_with(
            "folder", {"metadataObjects": {"$elemMatch": {"accessionId": self.accession_id, "schema": "study"}}}
        )
        self.assertEqual(result, (False, "", False))

    async def test_get_objects_folder_fails(self):
        """Test check object folder fails."""
        operator = FolderOperator(self.client)
        operator.db_service.query.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.get_collection_objects(self.folder_id, "study")

    async def test_get_objects_folder_passes(self):
        """Test get objects from folder returns proper data."""
        operator = FolderOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([self.test_folder])
        result = await operator.get_collection_objects(self.folder_id, "study")
        operator.db_service.query.assert_called_once_with(
            "folder", {"$and": [{"metadataObjects": {"$elemMatch": {"schema": "study"}}}, {"folderId": self.folder_id}]}
        )
        self.assertEqual(result, ["EGA1234567"])

    async def test_get_objects_folder_no_data(self):
        """Test get objects from folder returns no data."""
        operator = FolderOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([])
        result = await operator.get_collection_objects(self.folder_id, "study")
        operator.db_service.query.assert_called_once_with(
            "folder", {"$and": [{"metadataObjects": {"$elemMatch": {"schema": "study"}}}, {"folderId": self.folder_id}]}
        )
        self.assertEqual(result, [])

    async def test_reading_folder_works(self):
        """Test folder is read from db correctly."""
        operator = FolderOperator(self.client)
        operator.db_service.read.return_value = self.test_folder
        read_data = await operator.read_folder(self.folder_id)
        operator.db_service.read.assert_called_once_with("folder", self.folder_id)
        self.assertEqual(read_data, self.test_folder)

    async def test_folder_object_read_fails(self):
        """Test folder read fails."""
        operator = FolderOperator(self.client)
        operator.db_service.read.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.read_folder(self.folder_id)

    async def test_folder_update_passes_and_returns_id(self):
        """Test update method for folders works."""
        patch = [{"op": "add", "path": "/name", "value": "test2"}]
        operator = FolderOperator(self.client)
        operator.db_service.patch.return_value = True
        folder = await operator.update_folder(self.test_folder, patch)
        operator.db_service.patch.assert_called_once()
        self.assertEqual(folder["folderId"], self.folder_id)

    async def test_folder_update_fails_with_bad_patch(self):
        """Test folder update raises error with improper JSON Patch."""
        patch = [{"op": "replace", "path": "/nothing"}]
        operator = FolderOperator(self.client)
        operator.db_service.patch.return_value = False
        with self.assertRaises(HTTPBadRequest):
            await operator.update_folder(self.test_folder, patch)

    async def test_folder_object_update_fails(self):
        """Test folder update fails."""
        operator = FolderOperator(self.client)
        operator.db_service.patch.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.update_folder(self.test_folder, [])

    async def test_folder_object_remove_passes(self):
        """Test remove object method for folders works."""
        operator = FolderOperator(self.client)
        operator.db_service.remove.return_value = self.test_folder
        await operator.remove_object(self.test_folder, "study", self.accession_id)
        operator.db_service.remove.assert_called_once()
        self.assertEqual(len(operator.db_service.remove.mock_calls), 1)

    async def test_folder_object_remove_fails(self):
        """Test folder remove object fails."""
        operator = FolderOperator(self.client)
        operator.db_service.remove.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.remove_object(self.test_folder, "study", self.accession_id)

    async def test_check_folder_exists_fails(self):
        """Test fails exists fails."""
        operator = FolderOperator(self.client)
        operator.db_service.exists.return_value = False
        with self.assertRaises(HTTPNotFound):
            await operator.check_folder_exists(self.folder_id)
            operator.db_service.exists.assert_called_once()

    async def test_deleting_folder_passes(self):
        """Test folder is deleted correctly, if not published."""
        operator = FolderOperator(self.client)
        operator.db_service.published_folder.return_value = False
        operator.db_service.delete.return_value = True
        await operator.delete_folder(self.folder_id)
        operator.db_service.delete.assert_called_with("folder", self.folder_id)

    async def test_deleting_folder_fails_on_delete(self):
        """Test folder fails on db delete, if not published."""
        operator = FolderOperator(self.client)
        operator.db_service.published_folder.return_value = False
        operator.db_service.delete.return_value = False
        with self.assertRaises(HTTPBadRequest):
            await operator.delete_folder(self.folder_id)
            operator.db_service.delete.assert_called_with("folder", self.folder_id)

    async def test_delete_folder_fails(self):
        """Test folder delete fails."""
        operator = FolderOperator(self.client)
        operator.db_service.published_folder.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.delete_folder(self.folder_id)

    async def test_create_user_works_and_returns_userId(self):
        """Test create method for users work."""
        operator = UserOperator(self.client)
        data = "externalId", "name"
        operator.db_service.exists_user_by_external_id.return_value = None
        operator.db_service.create.return_value = True
        user = await operator.create_user(data)
        operator.db_service.create.assert_called_once()
        self.assertEqual(user, self.user_generated_id)

    async def test_create_user_on_create_fails(self):
        """Test create method fails on db create."""
        operator = UserOperator(self.client)
        data = "externalId", "name"
        operator.db_service.exists_user_by_external_id.return_value = None
        operator.db_service.create.return_value = False
        with self.assertRaises(HTTPBadRequest):
            await operator.create_user(data)
            operator.db_service.create.assert_called_once()

    async def test_check_user_doc_fails(self):
        """Test check user doc fails."""
        operator = UserOperator(self.client)
        operator.db_service.query.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.check_user_has_doc("folders", self.user_generated_id, self.folder_id)

    async def test_check_user_doc_passes(self):
        """Test check user doc returns proper data."""
        operator = UserOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator(["1"])
        result = await operator.check_user_has_doc("folders", self.user_generated_id, self.folder_id)
        operator.db_service.query.assert_called_once_with(
            "user", {"folders": {"$elemMatch": {"$eq": self.folder_id}}, "userId": self.user_generated_id}
        )
        self.assertTrue(result)

    async def test_check_user_doc_multiple_folders_fails(self):
        """Test check user doc returns multiple unique folders."""
        operator = UserOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator(["1", "2"])
        with self.assertRaises(HTTPUnprocessableEntity):
            await operator.check_user_has_doc("folders", self.user_generated_id, self.folder_id)
            operator.db_service.query.assert_called_once_with(
                "user", {"folders": {"$elemMatch": {"$eq": self.folder_id}}, "userId": self.user_generated_id}
            )

    async def test_check_user_doc_no_data(self):
        """Test check user doc returns no data."""
        operator = UserOperator(self.client)
        operator.db_service.query.return_value = AsyncIterator([])
        result = await operator.check_user_has_doc("folders", self.user_generated_id, self.folder_id)
        operator.db_service.query.assert_called_once_with(
            "user", {"folders": {"$elemMatch": {"$eq": self.folder_id}}, "userId": self.user_generated_id}
        )
        self.assertFalse(result)

    async def test_create_user_works_existing_userId(self):
        """Test create method for existing user."""
        operator = UserOperator(self.client)
        data = "eppn", "name"
        operator.db_service.exists_user_by_external_id.return_value = self.user_generated_id
        user = await operator.create_user(data)
        operator.db_service.create.assert_not_called()
        self.assertEqual(user, self.user_generated_id)

    async def test_create_user_fails(self):
        """Test create user fails."""
        data = "eppn", "name"
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

    async def test_check_user_exists_fails(self):
        """Test user exists fails."""
        operator = UserOperator(self.client)
        operator.db_service.exists.return_value = False
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

    async def test_user_objects_remove_passes(self):
        """Test remove objects method for users works."""
        operator = UserOperator(self.client)
        operator.db_service.exists.return_value = True
        operator.db_service.remove.return_value = self.test_user
        await operator.remove_objects(self.user_generated_id, "study", ["id"])
        operator.db_service.exists.assert_called_once()
        operator.db_service.remove.assert_called_once()
        self.assertEqual(len(operator.db_service.remove.mock_calls), 1)

    async def test_user_objects_remove_fails(self):
        """Test remove objects method for users fails."""
        operator = UserOperator(self.client)
        operator.db_service.exists.return_value = True
        operator.db_service.remove.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.remove_objects(self.user_generated_id, "study", ["id"])

    async def test_user_objects_append_passes(self):
        """Test append objects method for users works."""
        operator = UserOperator(self.client)
        operator.db_service.exists.return_value = True
        operator.db_service.append.return_value = self.test_user
        await operator.assign_objects(self.user_generated_id, "study", [])
        operator.db_service.exists.assert_called_once()
        operator.db_service.append.assert_called_once()
        self.assertEqual(len(operator.db_service.append.mock_calls), 1)

    async def test_user_objects_append_on_result_fails(self):
        """Test append objects method for users fails on db response validation."""
        operator = UserOperator(self.client)
        operator.db_service.exists.return_value = True
        operator.db_service.append.return_value = False
        with self.assertRaises(HTTPBadRequest):
            await operator.assign_objects(self.user_generated_id, "study", [])
            operator.db_service.exists.assert_called_once()
            operator.db_service.append.assert_called_once()

    async def test_user_objects_assing_fails(self):
        """Test append objects method for users fails."""
        operator = UserOperator(self.client)
        operator.db_service.exists.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.assign_objects(self.user_generated_id, "study", [])


if __name__ == "__main__":
    unittest.main()
