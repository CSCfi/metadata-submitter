"""Test CSC's LDAP service."""

import json
import os
import unittest

from unittest.mock import patch, MagicMock

from aiohttp import web

from metadata_backend.api.services.ldap import get_user_projects, verify_user_project


class TestLdap(unittest.TestCase):
    """Test CSC's LDAP service."""

    def test_get_user_projects_with_mocked_ldap(self):
        """Test get_user_projects with a mocked LDAP connection."""
        with patch.dict(os.environ, {
            "CSC_LDAP_HOST": "mockhost",
            "CSC_LDAP_USER": "mockuser",
            "CSC_LDAP_PASSWORD": "mockpassword"
        }):
            with patch('metadata_backend.api.services.ldap.Connection') as mock_connection:
                mock_conn_instance, mock_entry = MagicMock(), MagicMock()
                mock_entry.entry_to_json.return_value = json.dumps({
                    "dn": "ou=SP_SD-SUBMIT,ou=idm,dc=csc,dc=fi",
                    "attributes": {"CSCPrjNum": ["PRJ123"]}
                })
                mock_conn_instance.entries = [mock_entry]
                mock_connection.return_value.__enter__.return_value = mock_conn_instance

                projects = get_user_projects("testuser")
                self.assertEqual(projects, ["PRJ123"])

    def test_get_user_projects_errors(self) -> None:
        """Test get user projects fails when env variables are missing."""
        with self.assertRaises(RuntimeError) as e:
            get_user_projects("non_existent_user")
        self.assertEqual(str(e.exception), "Missing required environment variable: CSC_LDAP_HOST")


    def test_verify_user_projects(self) -> None:
        """Test verify user projects."""
        with patch('metadata_backend.api.services.ldap.get_user_projects', return_value=["123"]):
            # Should not raise
            verify_user_project("test_user", "123")

            with self.assertRaises(web.HTTPUnauthorized):
                verify_user_project("test_user", "-1")
