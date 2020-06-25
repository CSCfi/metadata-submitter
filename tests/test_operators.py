"""Test api endpoints from views module."""
import datetime
import unittest
from unittest.mock import patch, MagicMock
from metadata_backend.api.operators import Operator, XMLOperator


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


if __name__ == '__main__':
    unittest.main()
