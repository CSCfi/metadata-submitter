"""Test logger utilities."""

import unittest
from unittest.mock import MagicMock, patch

from metadata_backend.helpers.logger import log_debug_attributes, log_debug_json


class TestLogging(unittest.TestCase):
    """Test logger utilities."""

    @patch("metadata_backend.helpers.logger.LOG")
    def test_log_debug_attributes(self, mock_log: MagicMock) -> None:
        """Test log_debug_attributes."""

        log_debug_attributes({})

        messages = []
        for call in mock_log.debug.call_args_list:
            message = call[0][0]
            attr_name = call[0][1]
            attr_value = call[0][2]
            messages.append(message % (attr_name, attr_value))

        self.assertTrue("obj.__class__ = <class 'dict'>" in messages)

    @patch("metadata_backend.helpers.logger.LOG")
    def test_log_debug_json(self, mock_log: MagicMock) -> None:
        """Test log_debug_json."""

        log_debug_json({"name": "test_name", "value": 42})

        mock_log.debug.assert_called_once()
        args, _ = mock_log.debug.call_args
        logged_output = args[0]
        expected_output = "{\n" '    "name": "test_name",\n' '    "value": 42\n' "}"
        self.assertEqual(logged_output, expected_output)
