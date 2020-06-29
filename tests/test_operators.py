"""Test api endpoints from views module."""
import re
import datetime
import unittest
from aiohttp.web import HTTPNotFound, HTTPBadRequest
from unittest.mock import patch, MagicMock
from metadata_backend.api.operators import Operator, XMLOperator
from multidict import MultiDictProxy, MultiDict
from pymongo.errors import ConnectionFailure


class TestOperators(unittest.TestCase):
    """Test db-operator classes."""

    def setUp(self):
        """Configure default values for testing and mock dbservice."""
        class_dbservice = "metadata_backend.api.operators.DBService"
        self.accession_id = "EGA123456"
        self.patch_dbservice = patch(class_dbservice, spec=True)
        self.MockedDbService = self.patch_dbservice.start()
        self.patch_accession = patch(
            ("metadata_backend.api.operators."
             "BaseOperator._generate_accession_id"),
            return_value=self.accession_id,
            autospec=True)
        self.patch_accession.start()

    def tearDown(self):
        """Stop patchers."""
        self.patch_dbservice.stop()
        self.patch_accession.stop()

    def test_reading_metadata_works(self):
        """Test json is read from db correctly."""
        operator = Operator()
        data = {
            "_id": {
                "$oid": "5ecd28877f55c72e263f45c2"
            },
            "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
            "dateModified": datetime.datetime(2020, 6, 14, 0, 0),
            "accessionId": "EGA123456",
            "foo": "bar"
        }
        operator.db_service.read = MagicMock(return_value=data)
        r_data, c_type = operator.read_metadata_object("sample", "EGA123456")
        operator.db_service.read.assert_called_once_with("sample", "EGA123456")
        assert c_type == "application/json"

    def test_reading_with_non_valid_id_raises_error(self):
        """Test HTTPNotFound is raised."""
        operator = Operator()
        operator.db_service.read = MagicMock()
        operator.db_service.read.side_effect = HTTPNotFound
        with self.assertRaises(HTTPNotFound):
            operator.read_metadata_object("study", "EGA123456")

    def test_db_error_raises_400_error(self):
        """Test HTTPBadRequest is raised."""
        operator = Operator()
        operator.db_service.read = MagicMock()
        operator.db_service.read.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            operator.read_metadata_object("study", "EGA123456")

    def test_reading_metadata_works_with_xml(self):
        """Test xml is read from db correctly."""
        operator = XMLOperator()
        data = {
            "accessionId": "EGA123456",
            "content": "<TEST></TEST>"
        }
        operator.db_service.read = MagicMock(return_value=data)
        r_data, c_type = operator.read_metadata_object("sample", "EGA123456")
        operator.db_service.read.assert_called_once_with("sample", "EGA123456")
        assert c_type == "text/xml"
        assert r_data == data["content"]

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
        result = Operator()._format_single_dict("study", study_test)
        assert result["publishDate"] == "2020-06-14T00:00:00"
        assert result["dateCreated"] == "2020-06-14T00:00:00"
        assert result["dateModified"] == "2020-06-14T00:00:00"
        with self.assertRaises(KeyError):
            result["_Id"]

    @patch('metadata_backend.api.operators.datetime')
    def test_create_works_and_correct_info_is_set(self, mocked_datetime):
        """Test operator creates object and adds necessary info."""
        mocked_datetime.utcnow.return_value = datetime.datetime(2020, 4, 14)
        operator = Operator()
        operator.db_service.create = MagicMock()
        operator._handle_data_and_add_to_db("study", {}, "EGA123")
        operator.db_service.create.assert_called_once_with("study", {
            "accessionId": "EGA123",
            "dateCreated": datetime.datetime(2020, 4, 14),
            "dateModified": datetime.datetime(2020, 4, 14),
            "publishDate": datetime.datetime(2020, 6, 14)
        })

    def test_deleting_metadata_deletes_json_and_xml(self):
        """Test xml is read from db correctly."""
        operator = Operator()
        operator.db_service.delete = MagicMock()
        operator.delete_metadata_object("sample", "EGA123456")
        assert operator.db_service.delete.call_count == 2
        operator.db_service.delete.assert_called_with("sample", "EGA123456")

    def test_query_params_are_parsed_correctly(self):
        """Test that database is called with correct query."""
        operator = Operator()
        study_test = {
            "_id": {
                "$oid": "5ecd28877f55c72e263f45c2"
            },
            "publishDate": datetime.datetime(2020, 6, 14, 0, 0),
            "accessionId": "EDAG3945644754983408",
            "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
            "dateModified": datetime.datetime(2020, 6, 14, 0, 0)
        }
        operator.db_service.query = MagicMock(return_value=study_test)
        query = MultiDictProxy(MultiDict([("studyAttributes", "foo")]))
        operator.query_metadata_database("study", query)
        operator.db_service.query.assert_called_once_with(
            'study', {'$or': [
                {'studyAttributes.studyAttribute.tag':
                 re.compile('.*foo.*', re.IGNORECASE)},
                {'studyAttributes.studyAttribute.value':
                 re.compile('.*foo.*', re.IGNORECASE)}
            ]}
        )

    def test_non_working_query_params_are_not_passed_to_db_query(self):
        """Test that database is called with correct query."""
        operator = Operator()
        study_test = {
            "_id": {
                "$oid": "5ecd28877f55c72e263f45c2"
            },
            "publishDate": datetime.datetime(2020, 6, 14, 0, 0),
            "accessionId": "EDAG3945644754983408",
            "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
            "dateModified": datetime.datetime(2020, 6, 14, 0, 0)
        }
        operator.db_service.query = MagicMock(return_value=study_test)
        operator._format_read_data = MagicMock(return_value=study_test)
        query = MultiDictProxy(MultiDict([("swag", "littinen")]))
        operator.query_metadata_database("study", query)
        operator.db_service.query.assert_called_once_with('study', {})


if __name__ == '__main__':
    unittest.main()
