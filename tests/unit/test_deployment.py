"""Tests for deployment profiles."""

from unittest.mock import Mock

import pytest

from metadata_backend.api.dependencies import get_workflow
from metadata_backend.api.models.submission import SubmissionWorkflow
from metadata_backend.api.services.bigpicture import BigpictureSyncMetadataProvider
from metadata_backend.api.services.file import S3AllasFileProviderService, S3InboxSDAService
from metadata_backend.api.services.project import CscProjectService, NbisProjectService
from metadata_backend.api.services.submission.bigpicture_policy import BigpictureRemsLicenseProvider
from metadata_backend.conf.deployment import Deployment, deployment_config
from metadata_backend.deployment import CscDeploymentProfile, NbisDeploymentProfile, deployment_profile
from metadata_backend.services.admin_service import AdminServiceHandler
from metadata_backend.services.auth_service import AuthServiceHandler
from metadata_backend.services.datacite_service import DataciteServiceHandler
from metadata_backend.services.keystone_service import KeystoneServiceHandler
from metadata_backend.services.metax_service import MetaxServiceHandler
from metadata_backend.services.pid_service import PIDServiceHandler
from metadata_backend.services.ror_service import RorServiceHandler

# The endpoints served only by the CSC deployment, as (method, path) without the API prefix.
CSC_ONLY_ENDPOINTS = {
    ("post", "/v1/submissions"),
    ("patch", "/v1/submissions/{submissionId}"),
    ("delete", "/v1/submissions/{submissionId}"),
    ("get", "/v1/api/keys"),
    ("post", "/v1/api/keys"),
    ("delete", "/v1/api/keys"),
    ("get", "/v1/buckets"),
    ("get", "/v1/buckets/{bucket}/files"),
    ("put", "/v1/buckets/{bucket}"),
    ("head", "/v1/buckets/{bucket}"),
    ("get", "/login"),
    ("get", "/logout"),
}


@pytest.mark.parametrize("deployment", list(Deployment))
def test_every_deployment_has_profile(monkeypatch, deployment):
    monkeypatch.setenv("DEPLOYMENT", deployment)
    assert deployment_profile().deployment == deployment


@pytest.mark.parametrize(
    ("deployment", "expected_workflow"),
    [(Deployment.CSC, SubmissionWorkflow.SD), (Deployment.NBIS, SubmissionWorkflow.BP)],
)
def test_deployment_workflow(monkeypatch, deployment, expected_workflow):
    monkeypatch.setenv("DEPLOYMENT", deployment)
    assert deployment_profile().deployment == deployment
    assert get_workflow() == expected_workflow


def test_default_deployment(monkeypatch):
    monkeypatch.delenv("DEPLOYMENT", raising=False)
    assert deployment_profile().deployment == Deployment.CSC


def _endpoints(client) -> set[tuple[str, str]]:
    prefix = deployment_config().API_PREFIX
    paths = client.get(f"{prefix}/openapi.json").json()["paths"]
    return {(method, path.removeprefix(prefix)) for path, methods in paths.items() for method in methods}


def test_csc_endpoints(csc_client):
    assert CSC_ONLY_ENDPOINTS <= _endpoints(csc_client)


def test_nbis_endpoints(nbis_client):
    assert not CSC_ONLY_ENDPOINTS & _endpoints(nbis_client)


def test_csc_callback_endpoint(csc_client):
    # The OIDC callback endpoint is not in the OpenAPI schema. Without the OIDC parameters it is a user error.
    response = csc_client.get(f"{deployment_config().API_PREFIX}/callback", follow_redirects=False)
    assert response.status_code == 400


def test_nbis_callback_endpoint(nbis_client):
    response = nbis_client.get(f"{deployment_config().API_PREFIX}/callback", follow_redirects=False)
    assert response.status_code == 404


def _create_services(profile):
    # Return the handlers without registering them with an application. The tests use a
    # client fixture only for its environment, which the service configurations read.
    return profile.create_services(lambda handler: handler, Mock(), Mock())


def test_csc_services(csc_client):
    services = _create_services(CscDeploymentProfile())

    assert isinstance(services.project, CscProjectService)
    assert isinstance(services.file_provider, S3AllasFileProviderService)
    assert isinstance(services.metax, MetaxServiceHandler)
    assert isinstance(services.ror, RorServiceHandler)
    assert isinstance(services.pid, PIDServiceHandler)
    assert isinstance(services.keystone, KeystoneServiceHandler)
    assert isinstance(services.auth, AuthServiceHandler)
    assert services.datacite is None
    assert services.admin is None
    assert services.license_provider is None
    assert services.sync_provider is None


def test_nbis_services(nbis_client):
    services = _create_services(NbisDeploymentProfile())

    assert isinstance(services.project, NbisProjectService)
    assert isinstance(services.file_provider, S3InboxSDAService)
    assert isinstance(services.datacite, DataciteServiceHandler)
    assert isinstance(services.admin, AdminServiceHandler)
    assert isinstance(services.license_provider, BigpictureRemsLicenseProvider)
    assert isinstance(services.sync_provider, BigpictureSyncMetadataProvider)
    assert services.metax is None
    assert services.ror is None
    assert services.pid is None
    assert services.keystone is None
    assert services.auth is None
