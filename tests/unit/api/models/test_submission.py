"""Test submission models."""

import pytest
from pydantic import ValidationError

from metadata_backend.api.models.submission import Submission


@pytest.mark.parametrize("document", ["[1]", '"text"', "1"])
def test_submission_rejects_non_object(document: str) -> None:
    """Test that a document that is not a JSON object is a validation error, not a crash."""
    with pytest.raises(ValidationError):
        # The context is what the Sensitive Data submission service passes.
        Submission.model_validate_json(document, context={"projectId": "project", "workflow": "SD"})


def test_submission_rejects_non_object_creator() -> None:
    """Test that a creator that is not an object is a validation error, not a crash."""
    with pytest.raises(ValidationError):
        Submission.model_validate(
            {
                "projectId": "project",
                "name": "name",
                "title": "title",
                "description": "description",
                "workflow": "SD",
                "metadata": {"creators": ["creator"]},
            }
        )
