"""JSON serialisation."""

import json
from datetime import datetime
from typing import Sequence

from pydantic import BaseModel

# Supported by json.JSONEncoder
JSON = dict[str, "JSON"] | Sequence["JSON"] | str | int | float | bool | None


def to_json_dict(model: BaseModel) -> dict[str, JSON]:
    """
    Serialize the model to a JSON dictionary.

    :return: JSON dictionary.
    """
    return model.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )


def to_json(data: JSON | BaseModel) -> str:
    """
    Serialise the data to a JSON string.

    :param data: the data to convert to JSON.
    :return: A JSON string.
    """
    if isinstance(data, BaseModel):
        return json.dumps(to_json_dict(data))

    def default(o: object) -> str:
        if isinstance(o, datetime):
            # Convert datetime to ISO format without microseconds.
            return o.replace(microsecond=0).isoformat()
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    return json.dumps(data, default=default)
