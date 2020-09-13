"""Test api endpoints from views module."""
import datetime
import re
import unittest
from unittest.mock import MagicMock, patch

from aiohttp.web import HTTPBadRequest, HTTPNotFound
from aiounittest import AsyncTestCase, futurized
from aiounittest.mock import AsyncMockIterator
from jsonpatch import JsonPatch
from multidict import MultiDict, MultiDictProxy
from pymongo.errors import ConnectionFailure

from metadata_backend.api.operators import (
    FolderOperator,
    Operator,
    XMLOperator,
    UserOperator,
)


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
        self.folder_id = "FOL12345678"
        self.test_folder = {
            "folderId": self.folder_id,
            "name": "test",
            "description": "test folder",
            "published": False,
            "metadataObjects": [],
        }
        self.user_id = "USR12345678"
        self.test_user = {
            "userId": self.user_id,
            "username": "tester",
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
            ("metadata_backend.api.operators.FolderOperator." "_generate_folder_id"),
            return_value=self.folder_id,
            autospec=True,
        )
        self.patch_folder.start()
        self.patch_user = patch(
            ("metadata_backend.api.operators.UserOperator." "_generate_user_id"),
            return_value=self.user_id,
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
        """Test json is read from db correctly."""
        operator = Operator(self.client)
        data = {
            "dateCreated": datetime.datetime(2020, 6, 14, 0, 0),
            "dateModified": datetime.datetime(2020, 6, 14, 0, 0),
            "accessionId": "EGA123456",
            "foo": "bar",
        }
        operator.db_service.read.return_value = futurized(data)
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
        """Test xml is read from db correctly."""
        operator = XMLOperator(self.client)
        data = {"accessionId": "EGA123456", "content": "<TEST></TEST>"}
        operator.db_service.read.return_value = futurized(data)
        r_data, c_type = await operator.read_metadata_object("sample", "EGA123456")
        operator.db_service.read.assert_called_once_with("sample", "EGA123456")
        self.assertEqual(c_type, "text/xml")
        self.assertEqual(r_data, data["content"])

    async def test_reading_with_non_valid_id_raises_error(self):
        """Test read metadata HTTPNotFound is raised."""
        operator = Operator(self.client)
        operator.db_service.read.return_value = futurized(False)
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
        """Test create method for json works."""
        operator = Operator(self.client)
        data = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {"studyTitle": "Highly", "studyType": "Other"},
        }
        operator.db_service.create.return_value = futurized(True)
        accession = await operator.create_metadata_object("study", data)
        operator.db_service.create.assert_called_once()
        self.assertEqual(accession, self.accession_id)

    async def test_json_replace_passes_and_returns_accessionId(self):
        """Test replace method for json works."""
        accession = "EGA123456"
        data = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {"studyTitle": "Highly", "studyType": "Other"},
        }
        operator = Operator(self.client)
        operator.db_service.exists.return_value = futurized(True)
        operator.db_service.replace.return_value = futurized(True)
        await operator.replace_metadata_object("study", accession, data)
        operator.db_service.replace.assert_called_once()
        self.assertEqual(accession, self.accession_id)

    async def test_json_replace_raises_if_not_exists(self):
        """Test replace method raises error."""
        accession = "EGA123456"
        operator = Operator(self.client)
        operator.db_service.exists.return_value = futurized(False)
        operator.db_service.replace.return_value = futurized(True)
        with self.assertRaises(HTTPNotFound):
            await operator.replace_metadata_object("study", accession, {})
            operator.db_service.replace.assert_called_once()

    async def test_db_error_replace_raises_400_error(self):
        """Test replace metadata HTTPBadRequest is raised."""
        accession = "EGA123456"
        operator = Operator(self.client)
        operator.db_service.exists.return_value = futurized(True)
        operator.db_service.read.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.replace_metadata_object("study", accession, {})

    async def test_json_update_passes_and_returns_accessionId(self):
        """Test update method for json works."""
        accession = "EGA123456"
        data = {"centerName": "GEOM", "alias": "GSE10967"}
        db_data = {
            "centerName": "GEO",
            "alias": "GSE10966",
            "descriptor": {"studyTitle": "Highly", "studyType": "Other"},
        }
        operator = Operator(self.client)
        operator.db_service.read.return_value = futurized(db_data)
        operator.db_service.exists.return_value = futurized(True)
        operator.db_service.update.return_value = futurized(True)
        await operator.update_metadata_object("study", accession, data)
        operator.db_service.update.assert_called_once()
        self.assertEqual(accession, self.accession_id)

    async def test_json_update_raises_if_not_exists(self):
        """Test update method raises error."""
        accession = "EGA123456"
        operator = Operator(self.client)
        operator.db_service.exists.return_value = futurized(False)
        operator.db_service.replace.return_value = futurized(True)
        with self.assertRaises(HTTPNotFound):
            await operator.update_metadata_object("study", accession, {})
            operator.db_service.update.assert_called_once()

    async def test_db_error_update_raises_400_error(self):
        """Test update metadata HTTPBadRequest is raised."""
        accession = "EGA123456"
        operator = Operator(self.client)
        operator.db_service.exists.return_value = futurized(True)
        operator.db_service.read.side_effect = ConnectionFailure
        with self.assertRaises(HTTPBadRequest):
            await operator.update_metadata_object("study", accession, {})

    async def test_xml_create_passes_and_returns_accessionId(self):
        """Test create method for xml works. Patch json related calls."""
        operator = XMLOperator(self.client)
        operator.db_service.db_client = self.client
        operator.db_service.create.return_value = futurized(True)
        with patch(
            ("metadata_backend.api.operators.Operator." "_format_data_to_create_and_add_to_db"),
            return_value=futurized(self.accession_id),
        ):
            with patch("metadata_backend.api.operators.XMLToJSONParser"):
                accession = await operator.create_metadata_object("study", "<TEST></TEST>")
        operator.db_service.create.assert_called_once()
        self.assertEqual(accession, self.accession_id)

    async def test_correct_data_is_set_to_json_when_creating(self):
        """Test operator creates object and adds necessary info."""
        operator = Operator(self.client)
        with patch(
            ("metadata_backend.api.operators.Operator." "_insert_formatted_object_to_db"),
            return_value=futurized(self.accession_id),
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
        accession = "EGA123456"
        operator = Operator(self.client)
        with patch(
            "metadata_backend.api.operators.Operator._replace_object_from_db", return_value=futurized(self.accession_id)
        ):
            with patch("metadata_backend.api.operators.datetime") as m_date:
                m_date.utcnow.return_value = datetime.datetime(2020, 4, 14)
                with self.assertRaises(HTTPBadRequest):
                    await (
                        operator._format_data_to_replace_and_add_to_db(
                            "study",
                            accession,
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
        accession = "EGA123456"
        operator = Operator(self.client)
        with patch(
            "metadata_backend.api.operators.Operator._replace_object_from_db", return_value=futurized(self.accession_id)
        ) as mocked_insert:
            with patch("metadata_backend.api.operators.datetime") as m_date:
                m_date.utcnow.return_value = datetime.datetime(2020, 4, 14)
                acc = await (operator._format_data_to_replace_and_add_to_db("study", accession, {}))
                mocked_insert.assert_called_once_with(
                    "study",
                    accession,
                    {"accessionId": self.accession_id, "dateModified": datetime.datetime(2020, 4, 14)},
                )
            self.assertEqual(acc, self.accession_id)

    async def test_correct_data_is_set_to_json_when_updating(self):
        """Test operator updates object and adds necessary info."""
        accession = "EGA123456"
        operator = Operator(self.client)
        with patch(
            ("metadata_backend.api.operators.Operator." "_update_object_from_db"),
            return_value=futurized(self.accession_id),
        ) as mocked_insert:
            with patch("metadata_backend.api.operators.datetime") as m_date:
                m_date.utcnow.return_value = datetime.datetime(2020, 4, 14)
                acc = await (operator._format_data_to_update_and_add_to_db("study", accession, {}))
                mocked_insert.assert_called_once_with(
                    "study",
                    accession,
                    {"accessionId": self.accession_id, "dateModified": datetime.datetime(2020, 4, 14)},
                )
            self.assertEqual(acc, self.accession_id)

    async def test_wrong_data_is_set_to_json_when_updating(self):
        """Test operator update catches error."""
        accession = "EGA123456"
        operator = Operator(self.client)
        with patch(
            ("metadata_backend.api.operators.Operator." "_update_object_from_db"),
            return_value=futurized(self.accession_id),
        ):
            with patch("metadata_backend.api.operators.datetime") as m_date:
                m_date.utcnow.return_value = datetime.datetime(2020, 4, 14)
                with self.assertRaises(HTTPBadRequest):
                    await (
                        operator._format_data_to_update_and_add_to_db(
                            "study",
                            accession,
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
        xml_data = "<TEST></TEST>"
        with patch(
            ("metadata_backend.api.operators.Operator." "_format_data_to_create_and_add_to_db"),
            return_value=futurized(self.accession_id),
        ):
            with patch(
                ("metadata_backend.api.operators.XMLOperator." "_insert_formatted_object_to_db"),
                return_value=futurized(self.accession_id),
            ) as m_insert:
                with patch("metadata_backend.api.operators.XMLToJSONParser"):
                    acc = await (operator._format_data_to_create_and_add_to_db("study", xml_data))
                    m_insert.assert_called_once_with("study", {"accessionId": self.accession_id, "content": xml_data})
                    self.assertEqual(acc, self.accession_id)

    async def test_correct_data_is_set_to_xml_when_replacing(self):
        """Test XMLoperator replaces object and adds necessary info."""
        accession = "EGA123456"
        operator = XMLOperator(self.client)
        operator.db_service.db_client = self.client
        xml_data = "<TEST></TEST>"
        with patch(
            "metadata_backend.api.operators.Operator._format_data_to_replace_and_add_to_db",
            return_value=futurized(self.accession_id),
        ):
            with patch(
                "metadata_backend.api.operators.XMLOperator._replace_object_from_db",
                return_value=futurized(self.accession_id),
            ) as m_insert:
                with patch("metadata_backend.api.operators.XMLToJSONParser"):
                    acc = await (operator._format_data_to_replace_and_add_to_db("study", accession, xml_data))
                    m_insert.assert_called_once_with(
                        "study",
                        accession,
                        {"accessionId": self.accession_id, "content": xml_data},
                    )
                    self.assertEqual(acc, self.accession_id)

    async def test_deleting_metadata_deletes_json_and_xml(self):
        """Test metadata is deleted."""
        operator = Operator(self.client)
        operator.db_service.db_client = self.client
        operator.db_service.exists.return_value = futurized(True)
        operator.db_service.delete.return_value = futurized(True)
        await operator.delete_metadata_object("sample", "EGA123456")
        self.assertEqual(operator.db_service.delete.call_count, 2)
        operator.db_service.delete.assert_called_with("sample", "EGA123456")

    async def test_deleting_metadata_delete_raises(self):
        """Test error raised with delete."""
        operator = Operator(self.client)
        operator.db_service.db_client = self.client
        operator.db_service.exists.return_value = futurized(False)
        operator.db_service.delete.return_value = futurized(True)
        with self.assertRaises(HTTPNotFound):
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
        operator.db_service.query.return_value = MockCursor(study_test)
        query = MultiDictProxy(MultiDict([("studyAttributes", "foo")]))
        await operator.query_metadata_database("study", query, 1, 10)
        operator.db_service.query.assert_called_once_with(
            "study",
            {
                "$or": [
                    {"studyAttributes.tag": re.compile(".*foo.*", re.IGNORECASE)},
                    {"studyAttributes.value": re.compile(".*foo.*", re.IGNORECASE)},
                ]
            },
        )

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
        operator.db_service.query.return_value = MockCursor(study_test)
        query = MultiDictProxy(MultiDict([("swag", "littinen")]))
        with patch(
            "metadata_backend.api.operators.Operator._format_read_data",
            return_value=futurized(study_test),
        ):
            await operator.query_metadata_database("study", query, 1, 10)
        operator.db_service.query.assert_called_once_with("study", {})

    async def test_query_result_is_parsed_correctly(self):
        """Test json is read and correct pagination values are returned."""
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
        operator.db_service.query.return_value = MockCursor(multiple_result)
        operator.db_service.get_count.return_value = futurized(100)
        query = MultiDictProxy(MultiDict([]))
        (
            parsed,
            page_num,
            page_size,
            total_objects,
        ) = await operator.query_metadata_database("sample", query, 1, 10)
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
            return_value=futurized([]),
        ):
            with self.assertRaises(HTTPNotFound):
                await operator.query_metadata_database("study", query, 1, 10)

    async def test_query_skip_and_limit_are_set_correctly(self):
        """Test custom skip and limits."""
        operator = Operator(self.client)
        data = {"foo": "bar"}
        cursor = MockCursor([])
        operator.db_service.query.return_value = cursor
        with patch(
            "metadata_backend.api.operators.Operator._format_read_data",
            return_value=futurized(data),
        ):
            await operator.query_metadata_database("sample", {}, 3, 50)
            self.assertEqual(cursor._skip, 100)
            self.assertEqual(cursor._limit, 50)

    async def test_create_folder_works_and_returns_folderId(self):
        """Test create method for folders work."""
        operator = FolderOperator(self.client)
        data = {"name": "test", "description": "test folder"}
        operator.db_service.create.return_value = futurized(True)
        folder = await operator.create_folder(data)
        operator.db_service.create.assert_called_once()
        self.assertEqual(folder, self.folder_id)

    async def test_query_folders_empty_list(self):
        """Test query returns empty list."""
        operator = FolderOperator(self.client)
        cursor = MockCursor([])
        operator.db_service.query.return_value = cursor
        folders = await operator.query_folders({})
        operator.db_service.query.assert_called_once()
        self.assertEqual(folders, [])

    async def test_query_folders_1_item(self):
        """Test query returns a list with item."""
        operator = FolderOperator(self.client)
        cursor = MockCursor([{"name": "folder"}])
        operator.db_service.query.return_value = cursor
        folders = await operator.query_folders({})
        operator.db_service.query.assert_called_once()
        self.assertEqual(folders, [{"name": "folder"}])

    async def test_reading_folder_works(self):
        """Test folder is read from db correctly."""
        operator = FolderOperator(self.client)
        operator.db_service.exists.return_value = futurized(True)
        operator.db_service.read.return_value = futurized(self.test_folder)
        read_data = await operator.read_folder(self.folder_id)
        operator.db_service.exists.assert_called_once()
        operator.db_service.read.assert_called_once_with("folder", self.folder_id)
        self.assertEqual(read_data, self.test_folder)

    async def test_folder_update_passes_and_returns_id(self):
        """Test update method for folders works."""
        patch = JsonPatch([{"op": "add", "path": "/name", "value": "test2"}])
        operator = FolderOperator(self.client)
        operator.db_service.exists.return_value = futurized(True)
        operator.db_service.read.return_value = futurized(self.test_folder)
        operator.db_service.update.return_value = futurized(True)
        folder = await operator.update_folder(self.test_folder, patch)
        operator.db_service.exists.assert_called_once()
        operator.db_service.update.assert_called_once()
        self.assertEqual(len(operator.db_service.read.mock_calls), 2)
        self.assertEqual(folder["folderId"], self.folder_id)

    async def test_folder_update_fails_with_bad_patch(self):
        """Test folder update raises error with improper JSON Patch."""
        patch = JsonPatch([{"op": "replace", "path": "nothing"}])
        operator = FolderOperator(self.client)
        operator.db_service.exists.return_value = futurized(True)
        operator.db_service.read.return_value = futurized(self.test_folder)
        with self.assertRaises(HTTPBadRequest):
            await operator.update_folder(self.test_folder, patch)
            operator.db_service.exists.assert_called_once()
            operator.db_service.read.assert_called_once()

    async def test_deleting_folder_passes(self):
        """Test folder is deleted correctly."""
        operator = FolderOperator(self.client)
        operator.db_service.exists.return_value = futurized(True)
        operator.db_service.delete.return_value = futurized(True)
        await operator.delete_folder(self.folder_id)
        operator.db_service.delete.assert_called_with("folder", "FOL12345678")

    async def test_create_user_works_and_returns_userId(self):
        """Test create method for users work."""
        operator = UserOperator(self.client)
        data = {}
        operator.db_service.create.return_value = futurized(True)
        folder = await operator.create_user(data)
        operator.db_service.create.assert_called_once()
        self.assertEqual(folder, self.user_id)

    async def test_reading_user_works(self):
        """Test user object is read from db correctly."""
        operator = UserOperator(self.client)
        operator.db_service.exists.return_value = futurized(True)
        operator.db_service.read.return_value = futurized(self.test_user)
        read_data = await operator.read_user(self.user_id)
        operator.db_service.exists.assert_called_once()
        operator.db_service.read.assert_called_once_with("user", self.user_id)
        self.assertEqual(read_data, self.test_user)

    async def test_user_update_passes_and_returns_id(self):
        """Test update method for users works."""
        patch = JsonPatch([{"op": "add", "path": "/name", "value": "test2"}])
        operator = UserOperator(self.client)
        operator.db_service.exists.return_value = futurized(True)
        operator.db_service.read.return_value = futurized(self.test_user)
        operator.db_service.update.return_value = futurized(True)
        user = await operator.update_user(self.test_user, patch)
        operator.db_service.exists.assert_called_once()
        operator.db_service.update.assert_called_once()
        self.assertEqual(len(operator.db_service.read.mock_calls), 2)
        self.assertEqual(user["userId"], self.user_id)

    async def test_user_update_fails_with_bad_patch(self):
        """Test user update raises error with improper JSON Patch."""
        patch = JsonPatch([{"op": "replace", "path": "nothing"}])
        operator = UserOperator(self.client)
        operator.db_service.exists.return_value = futurized(True)
        operator.db_service.read.return_value = futurized(self.test_user)
        with self.assertRaises(HTTPBadRequest):
            await operator.update_user(self.test_user, patch)
            operator.db_service.exists.assert_called_once()
            operator.db_service.read.assert_called_once()

    async def test_deleting_user_passes(self):
        """Test user is deleted correctly."""
        operator = UserOperator(self.client)
        operator.db_service.exists.return_value = futurized(True)
        operator.db_service.delete.return_value = futurized(True)
        await operator.delete_user(self.user_id)
        operator.db_service.delete.assert_called_with("user", "USR12345678")


if __name__ == "__main__":
    unittest.main()
