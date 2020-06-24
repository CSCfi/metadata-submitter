"""Test api endpoints from views module."""
import datetime
import unittest
from unittest.mock import patch
from metadata_backend.api.operators import Operator


class TestOperators(unittest.TestCase):
    """Test schema loader."""

    def setUp(self):
        """Configure default values for testing and mock dbservice."""
        class_dbservice = "metadata_backend.api.operators.DBService"
        self.patch_dbservice = patch(class_dbservice, spec=True)
        self.MockedDbService = self.patch_dbservice.start()

    def test_operator_fixes_datetime_presentation(self):
        """Test datetime is fixed from datetime object to ISO8601."""
        study_test = {
            "_id": {
                "$oid": "5ecd28877f55c72e263f45c2"
            },
            "publishDate": datetime.datetime(2020, 6, 14, 0, 0),
            "accessionId": "EDAG3945644754983408"
        }
        operator = Operator()
        result = operator._format_publish_date(study_test)
        assert result["publishDate"] == "2020-06-14T00:00:00"


if __name__ == '__main__':
    unittest.main()
