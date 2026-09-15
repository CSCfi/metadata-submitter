import pytest
from starlette import status

from metadata_backend.api.exceptions import (
    AppException,
    ServiceHandlerSystemException,
    SystemException,
    UserException,
    external_service_call,
)

MESSAGE = "Failed to do the thing."
RETRY_MESSAGE = f"{MESSAGE} Please try again later."


@pytest.mark.parametrize(
    "raised, expected_type, expected_message, expected_status_code",
    [
        (UserException("test1"), UserException, "test1", status.HTTP_400_BAD_REQUEST),
        (SystemException("test2"), SystemException, RETRY_MESSAGE, status.HTTP_500_INTERNAL_SERVER_ERROR),
        (ServiceHandlerSystemException("test3"), SystemException, RETRY_MESSAGE, status.HTTP_502_BAD_GATEWAY),
        (RuntimeError("test4"), SystemException, RETRY_MESSAGE, status.HTTP_500_INTERNAL_SERVER_ERROR),
    ],
)
def test_external_service_call_with_error(raised, expected_type, expected_message, expected_status_code):
    with pytest.raises(AppException) as exc:
        with external_service_call(MESSAGE):
            raise raised

    assert type(exc.value) is expected_type
    assert str(exc.value) == expected_message
    assert exc.value.status_code == expected_status_code


def test_external_service_call_without_error():
    with external_service_call(MESSAGE):
        result = "done"

    assert result == "done"


def test_external_service_call_chains_error():
    original = RuntimeError("test4")

    with pytest.raises(AppException) as exc:
        with external_service_call(MESSAGE):
            raise original

    assert exc.value.__cause__ is original
