"""Test configuration."""

import os
from unittest import TestCase, mock

from metadata_backend.conf.conf import set_conf


class ConfigTests(TestCase):
    """Test configuration."""

    @mock.patch.dict(os.environ, {"MONGO_DATABASE": "ceva"})
    @mock.patch.dict(os.environ, {"MONGO_SSL": "True"})
    @mock.patch.dict(os.environ, {"MONGO_SSL_CA": "ca.crt"})
    @mock.patch.dict(os.environ, {"MONGO_SSL_CLIENT_CERT_KEY": "client.key"})
    @mock.patch.dict(os.environ, {"MONGO_AUTHDB": "admin"})
    def test_all_values(self):
        """Test all env values set."""
        url, mongo_database = set_conf()
        self.assertEqual(
            mongo_database,
            "ceva",
        )
        _params = "ceva?tls=true&tlsCAFile=ca.crt&tlsCertificateKeyFile=client.key&authSource=admin"
        self.assertEqual(
            url,
            f"mongodb://admin:admin@localhost:27017/{_params}",
        )

    @mock.patch.dict(os.environ, {"MONGO_DATABASE": "ceva"})
    @mock.patch.dict(os.environ, {"MONGO_SSL": "False"})
    @mock.patch.dict(os.environ, {"MONGO_AUTHDB": "admin"})
    def test_no_ssl_value(self):
        """Test no ssl env values set."""
        url, mongo_database = set_conf()
        self.assertEqual(
            mongo_database,
            "ceva",
        )
        self.assertEqual(
            url,
            "mongodb://admin:admin@localhost:27017/ceva?authSource=admin",
        )

    @mock.patch.dict(os.environ, {"MONGO_DATABASE": "ceva"})
    @mock.patch.dict(os.environ, {"MONGO_DATABASE": "ceva"})
    @mock.patch.dict(os.environ, {"MONGO_SSL": "True"})
    @mock.patch.dict(os.environ, {"MONGO_SSL_CA": "ca.crt"})
    @mock.patch.dict(os.environ, {"MONGO_SSL_CLIENT_CERT_KEY": "client.key"})
    def test_ssl_no_db_value(self):
        """Test ssl env values set, but no db."""
        url, _ = set_conf()
        _params = "ceva?tls=true&tlsCAFile=ca.crt&tlsCertificateKeyFile=client.key"
        self.assertEqual(
            url,
            f"mongodb://admin:admin@localhost:27017/{_params}",
        )
