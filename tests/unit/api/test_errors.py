"""Test API middlewares."""

from metadata_backend.conf.conf import API_PREFIX
from tests.unit.patches.user import patch_verify_authorization


def test_fastapi_routing_error(csc_client, nbis_client):
    """Test FastAPI routing error that happens before middleware converts errors to problem JSON."""
    with patch_verify_authorization:
        for client in (csc_client, nbis_client):
            response = client.get(f"{API_PREFIX}/invalid_url")
            data = response.json()
            assert response.status_code == 404
            # Unknown routes bypass middleware.
            assert data == {"detail": "Not Found"}


def test_problem_json_get_submissions_error(csc_client, nbis_client):
    """Test middleware converts errors to problem JSON when getting an unknown submission."""
    with patch_verify_authorization:
        for client in (csc_client, nbis_client):
            response = client.get(f"{API_PREFIX}/submissions/unknown")
            data = response.json()
            assert response.status_code == 404
            assert data == {
                "detail": "Submission 'unknown' not found.",
                "instance": "/v1/submissions/unknown",
                "status": 404,
                "title": "Not Found",
                "type": "about:blank",
            }


def test_problem_json_post_submissions_error(csc_client):
    """Test middleware converts errors to problem JSON when posting an invalid submission JSON."""
    with patch_verify_authorization:
        response = csc_client.post(f"{API_PREFIX}/submissions", json={})
        data = response.json()
        assert response.status_code == 400
        assert data == {
            "detail": "Validation error",
            "errors": [
                {"field": "body.projectId", "message": "Field required"},
                {"field": "body.name", "message": "Field required"},
                {"field": "body.title", "message": "Field required"},
                {"field": "body.description", "message": "Field required"},
                {"field": "body.workflow", "message": "Field required"},
            ],
            "instance": "/v1/submissions",
            "status": 400,
            "title": "Bad Request",
            "type": "about:blank",
        }
