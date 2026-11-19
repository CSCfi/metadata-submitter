"""Test the OIDC configuration."""

import pytest

from metadata_backend.conf.oidc import OIDCConfig


@pytest.mark.parametrize(
    ("base_url", "api_prefix", "expected"),
    [
        ("https://host", "", "https://host/callback"),
        ("https://host/", "", "https://host/callback"),
        ("https://host/app", "", "https://host/app/callback"),
        ("https://host/app/", "", "https://host/app/callback"),
        ("https://host/app", "/api", "https://host/app/api/callback"),
        ("https://host/app/", "/api/", "https://host/app/api/callback"),
        ("https://host", "api", "https://host/api/callback"),
    ],
)
def test_callback_url(monkeypatch, base_url, api_prefix, expected):
    monkeypatch.setenv("API_PREFIX", api_prefix)

    assert OIDCConfig(BASE_URL=base_url).callback_url == expected
