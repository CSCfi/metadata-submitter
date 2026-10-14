"""Test API error responses."""

import pytest

from metadata_backend.api.errors import ServerErrorProblem, UserErrorProblem, ValidationErrorProblem
from metadata_backend.conf.deployment import deployment_config
from tests.unit.patches.user import patch_get_user_projects, patch_verify_authorization, patch_verify_user_project


def test_unknown_path_error(csc_client, nbis_client):
    """Test that a request to an unknown path is a user error."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    with patch_verify_authorization:
        for client in (csc_client, nbis_client):
            response = client.get(f"{api_prefix_v1}/invalid_url")
            data = response.json()
            assert response.status_code == 404
            assert response.headers["content-type"] == "application/problem+json"
            UserErrorProblem.model_validate(data)
            assert data["errors"] == ["Not Found"]


def test_unsupported_method_error(nbis_client):
    """Test that a request with a method that the path does not support is a user error."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    with patch_verify_authorization:
        # Creating submissions is not supported in the NBIS deployment.
        response = nbis_client.post(f"{api_prefix_v1}/submissions", json={})
        data = response.json()
        assert response.status_code == 405
        assert response.headers["allow"] == "GET"
        UserErrorProblem.model_validate(data)
        assert data["errors"] == ["Method Not Allowed"]


def test_problem_json_get_submissions_error(csc_client, nbis_client):
    """Test middleware converts errors to problem JSON when getting an unknown submission."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    with patch_verify_authorization, patch_get_user_projects, patch_verify_user_project:
        for client in (csc_client, nbis_client):
            response = client.get(f"{api_prefix_v1}/submissions/unknown")
            data = response.json()
            assert response.status_code == 404
            UserErrorProblem.model_validate(data)
            assert data == {
                "detail": "User error",
                "errors": ["Submission 'unknown' not found."],
                "instance": f"{deployment_config().API_PREFIX_V1}/submissions/unknown",
                "status": 404,
                "title": "Not Found",
                "type": "about:blank",
            }


def test_problem_json_post_submissions_error(csc_client):
    """Test middleware converts errors to problem JSON when posting an invalid submission JSON."""
    api_prefix_v1 = deployment_config().API_PREFIX_V1
    with patch_verify_authorization:
        response = csc_client.post(f"{api_prefix_v1}/submissions", json={})
        data = response.json()
        assert response.status_code == 400
        ValidationErrorProblem.model_validate(data)
        assert data == {
            "detail": "Validation error",
            "errors": [
                {"field": "body.projectId", "message": "Field required"},
                {"field": "body.name", "message": "Field required"},
                {"field": "body.title", "message": "Field required"},
                {"field": "body.description", "message": "Field required"},
            ],
            "instance": f"{api_prefix_v1}/submissions",
            "status": 400,
            "title": "Bad Request",
            "type": "about:blank",
        }


@pytest.mark.parametrize("client_fixture", ["csc_client", "nbis_client"])
def test_openapi_error_responses(client_fixture, request):
    """Test that every operation documents its problem JSON error responses."""
    client = request.getfixturevalue(client_fixture)
    schema = client.get("/openapi.json").json()

    schemas = schema["components"]["schemas"]
    for model in (UserErrorProblem, ValidationErrorProblem, ServerErrorProblem):
        assert schemas[model.__name__]["title"] == model.__name__
    assert schemas["FieldError"]["required"] == ["field", "message"]
    assert schemas["UserErrorProblem"]["properties"]["detail"]["const"] == "User error"
    assert schemas["ValidationErrorProblem"]["properties"]["detail"]["const"] == "Validation error"
    assert "errors" not in schemas["ServerErrorProblem"]["properties"]
    # FastAPI's default 422 response is never returned.
    assert "HTTPValidationError" not in schemas

    def ref(name: str) -> dict[str, str]:
        return {"$ref": f"#/components/schemas/{name}"}

    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            responses = operation["responses"]
            assert "422" not in responses, (method, path)
            assert responses["4XX"]["content"]["application/problem+json"]["schema"] == ref("UserErrorProblem")
            assert responses["5XX"]["content"]["application/problem+json"]["schema"] == ref("ServerErrorProblem")

    # An operation with parameters may return either 400 shape.
    bad_request = schema["paths"]["/v1/submissions"]["get"]["responses"]["400"]
    bad_request_schema = bad_request["content"]["application/problem+json"]["schema"]
    assert bad_request_schema["oneOf"] == [ref("UserErrorProblem"), ref("ValidationErrorProblem")]

    # An operation without parameters cannot fail validation.
    assert "400" not in schema["paths"]["/v1/users"]["get"]["responses"]
