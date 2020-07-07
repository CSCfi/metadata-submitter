"""Test api endpoints from views module."""
import re
import datetime
import unittest
from aiohttp.web import HTTPNotFound, HTTPBadRequest
from aiounittest import AsyncTestCase, futurized
from aiounittest.mock import AsyncMockIterator
from unittest.mock import patch, MagicMock
from metadata_backend.api.operators import Operator, XMLOperator
from multidict import MultiDictProxy, MultiDict
from pymongo.errors import ConnectionFailure


class MockCursor(AsyncMockIterator):
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


class TestOperators(AsyncTestCase):
    """Test db-operator classes."""

    def setUp(self):
        """Configure default values for testing and mock dbservice.

        Monkey patches MagicMock to work with async / await, then sets up
        other patches and mocks for tests.
        """
        async def async_patch():
            pass
        MagicMock.__await__ = lambda x: async_patch().__await__()
        self.client = MagicMock()
        self.accession_id = "EGA123456"
        class_dbservice = "metadata_backend.api.operators.DBService"
        self.patch_dbservice = patch(class_dbservice, spec=True)
        self.MockedDbService = self.patch_dbservice.start()
        self.patch_accession = patch(
            "metadata_backend.api.operators.Operator._generate_accession_id",
            return_value=self.accession_id,
            autospec=True)
        self.patch_accession.start()

    def tearDown(self):
        """Stop patchers."""
        self.patch_dbservice.stop()
        self.patch_accession.stop()

    async def test_reading_metadata_works(self):
        """Test json is read from db correctly."""
        operator = Operator(self.client)
        data = {
            "_id": {
                "$oid": "5ecd28877f55c72e263f45c2"
            },
            "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
            "dateModified": datetime.datetime(2020, 6, 14, 0, 0),
            "accessionId": "EGA123456",
            "foo": "bar"
        }
        operator.db_service.read.return_value = futurized(data)
        read_data, c_type = await operator.read_metadata_object("sample",
                                                                "EGA123456")
        operator.db_service.read.assert_called_once_with("sample", "EGA123456")
        assert c_type == "application/json"
        assert read_data == {"dateCreated": "2020-06-14T00:00:00",
                             "dateModified": "2020-06-14T00:00:00",
                             "accessionId": "EGA123456",
                             "foo": "bar"}

    async def test_reading_metadata_works_with_xml(self):
        """Test xml is read from db correctly."""
        operator = XMLOperator(self.client)
        data = {
            "accessionId": "EGA123456",
            "content": "<TEST></TEST>"
        }
        operator.db_service.read.return_value = futurized(data)
        r_data, c_type = await operator.read_metadata_object("sample",
                                                             "EGA123456")
        operator.db_service.read.assert_called_once_with("sample", "EGA123456")
        assert c_type == "text/xml"
        assert r_data == data["content"]

    async def test_reading_with_non_valid_id_raises_error(self):
        """Test HTTPNotFound is raised."""
        operator = Operator(self.client)
        operator.db_service.read.side_effect = HTTPNotFound
        with self.assertRaises(HTTPNotFound):
            await operator.read_metadata_object("study", "EGA123456")

    async def test_db_error_raises_400_error(self):
        """Test HTTPBadRequest is raised."""
        operator = Operator(self.client)
        operator.db_service.read.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.read_metadata_object("study", "EGA123456")

    def test_operator_fixes_single_document_presentation(self):
        """Test datetime is fixed and id removed."""
        study_test = {
            "_id": {
                "$oid": "5ecd28877f55c72e263f45c2"
            },
            "publishDate": datetime.datetime(2020, 6, 14, 0, 0),
            "accessionId": "EDAG3945644754983408",
            "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
            "dateModified": datetime.datetime(2020, 6, 14, 0, 0)
        }
        result = Operator(self.client)._format_single_dict("study", study_test)
        assert result["publishDate"] == "2020-06-14T00:00:00"
        assert result["dateCreated"] == "2020-06-14T00:00:00"
        assert result["dateModified"] == "2020-06-14T00:00:00"
        with self.assertRaises(KeyError):
            result["_Id"]

    async def test_json_create_passes_and_returns_accessionId(self):
        """Test create method for json works."""
        operator = Operator(self.client)
        operator.db_service.create.return_value = futurized(True)
        accession = await operator.create_metadata_object("study", {})
        operator.db_service.create.assert_called_once()
        assert accession == self.accession_id

    async def test_xml_create_passes_and_returns_accessionId(self):
        """Test create method for xml works. Patch json related calls."""
        operator = XMLOperator(self.client)
        operator.db_service.db_client = self.client
        operator.db_service.create.return_value = futurized(True)
        with patch(("metadata_backend.api.operators.Operator."
                    "_format_data_to_create_and_add_to_db"),
                   return_value=futurized(self.accession_id)):
            with patch("metadata_backend.api.operators.XMLToJSONParser"):
                accession = await operator.create_metadata_object(
                    "study", "<TEST></TEST>")
        operator.db_service.create.assert_called_once()
        assert accession == self.accession_id

    async def test_correct_data_is_set_to_json_when_creating(self):
        """Test operator creates object and adds necessary info."""
        operator = Operator(self.client)
        with patch(("metadata_backend.api.operators.Operator."
                    "_insert_formatted_object_to_db"),
                   return_value=futurized(self.accession_id)) as mocked_insert:
            with patch("metadata_backend.api.operators.datetime") as m_date:
                m_date.utcnow.return_value = datetime.datetime(2020, 4, 14)
                acc = await (operator._format_data_to_create_and_add_to_db(
                    "study", {}))
                mocked_insert.assert_called_once_with(
                    "study", {"accessionId": self.accession_id,
                              "dateCreated": datetime.datetime(2020, 4, 14),
                              "dateModified": datetime.datetime(2020, 4, 14),
                              "publishDate": datetime.datetime(2020, 6, 14)})
            assert acc == self.accession_id

    async def test_correct_data_is_set_to_xml_when_creating(self):
        """Test XMLoperator creates object and adds necessary info."""
        operator = XMLOperator(self.client)
        operator.db_service.db_client = self.client
        xml_data = "<TEST></TEST>"
        with patch(("metadata_backend.api.operators.Operator."
                    "_format_data_to_create_and_add_to_db"),
                   return_value=futurized(self.accession_id)):
            with patch(("metadata_backend.api.operators.XMLOperator."
                        "_insert_formatted_object_to_db"),
                       return_value=futurized(self.accession_id)) as m_insert:
                with patch("metadata_backend.api.operators.XMLToJSONParser"):
                    acc = await (operator.
                                 _format_data_to_create_and_add_to_db("study",
                                                                      xml_data)
                                 )
                    m_insert.assert_called_once_with("study", {
                        "accessionId": self.accession_id,
                        "content": xml_data})
                    assert acc == self.accession_id

    async def test_deleting_metadata_deletes_json_and_xml(self):
        """Test xml is read from db correctly."""
        operator = Operator(self.client)
        operator.db_service.db_client = self.client
        operator.db_service.delete.return_value = futurized(True)
        await operator.delete_metadata_object("sample", "EGA123456")
        assert operator.db_service.delete.call_count == 2
        operator.db_service.delete.assert_called_with("sample", "EGA123456")

    async def test_working_query_params_are_passed_to_db_query(self):
        """Test that database is called with correct query."""
        operator = Operator(self.client)
        study_test = [{
            "_id": {
                "$oid": "5ecd28877f55c72e263f45c2"
            },
            "publishDate": datetime.datetime(2020, 6, 14, 0, 0),
            "accessionId": "EDAG3945644754983408",
            "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
            "dateModified": datetime.datetime(2020, 6, 14, 0, 0)
        }]
        operator.db_service.query.return_value = MockCursor(study_test)
        query = MultiDictProxy(MultiDict([("studyAttributes", "foo")]))
        await operator.query_metadata_database("study", query, 1, 10)
        operator.db_service.query.assert_called_once_with(
            'study', {'$or': [
                {'studyAttributes.tag':
                 re.compile('.*foo.*', re.IGNORECASE)},
                {'studyAttributes.value':
                 re.compile('.*foo.*', re.IGNORECASE)}
            ]}
        )

    async def test_non_working_query_params_are_not_passed_to_db_query(self):
        """Test that database with empty query, when url params are wrong."""
        operator = Operator(self.client)
        study_test = [{
            "_id": {
                "$oid": "5ecd28877f55c72e263f45c2"
            },
            "publishDate": datetime.datetime(2020, 6, 14, 0, 0),
            "accessionId": "EDAG3945644754983408",
            "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
            "dateModified": datetime.datetime(2020, 6, 14, 0, 0)
        }]
        operator.db_service.query.return_value = MockCursor(study_test)
        query = MultiDictProxy(MultiDict([("swag", "littinen")]))
        with patch("metadata_backend.api.operators.Operator._format_read_data",
                   return_value=futurized(study_test)):
            await operator.query_metadata_database("study", query, 1, 10)
        operator.db_service.query.assert_called_once_with('study', {})

    async def test_query_result_is_parsed_correctly(self):
        """Test json is read and correct pagination values are returned."""
        operator = Operator(self.client)
        multiple_result = [
            {
                "_id": {
                    "$oid": "5ecd28877f55c72e263f45c2"
                },
                "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
                "dateModified": datetime.datetime(2020, 6, 14, 0, 0),
                "accessionId": "EGA123456",
                "foo": "bar"
            }, {
                "_id": {
                    "$oid": "5ecd28877f55c72e263f45c2"
                },
                "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
                "dateModified": datetime.datetime(2020, 6, 14, 0, 0),
                "accessionId": "EGA123456",
                "foo": "bar"
            }
        ]
        operator.db_service.query.return_value = MockCursor(multiple_result)
        operator.db_service.get_count.return_value = futurized(100)
        query = MultiDictProxy(MultiDict([]))
        parsed, page_num, page_size, total_objects = (
            await operator.query_metadata_database("sample", query, 1, 10))
        for doc in parsed:
            assert doc["dateCreated"] == "2020-06-14T00:00:00"
            assert doc["dateModified"] == "2020-06-14T00:00:00"
            assert doc["accessionId"] == "EGA123456"
        assert page_num == 1
        assert page_size == 2
        assert total_objects == 100

    async def test_non_empty_query_result_raises_notfound(self):
        """Test that 404 is raised with empty query result."""
        operator = Operator(self.client)
        operator.db_service.query = MagicMock()
        query = MultiDictProxy(MultiDict([]))
        with patch("metadata_backend.api.operators.Operator._format_read_data",
                   return_value=futurized([])):
            with self.assertRaises(HTTPNotFound):
                await operator.query_metadata_database("study", query, 1, 10)

    async def test_query_skip_and_limit_are_set_correctly(self):
        """Test custom skip and limits."""
        operator = Operator(self.client)
        data = {"foo": "bar"}
        cursor = MockCursor([])
        operator.db_service.query.return_value = cursor
        with patch("metadata_backend.api.operators.Operator._format_read_data",
                   return_value=futurized(data)):
            await operator.query_metadata_database("sample", {}, 3, 50)
            assert cursor._skip == 100
            assert cursor._limit == 50


if __name__ == '__main__':
    unittest.main()
