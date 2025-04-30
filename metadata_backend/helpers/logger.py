"""Logging formatting and functions for debugging."""

import logging
import os
from typing import Any

import ujson

FORMAT = "[{asctime}][{name}][{process} {processName:<12}] [{levelname:8s}](L:{lineno}) {funcName}: {message}"
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S", style="{")

LOG = logging.getLogger("server")
LOG.setLevel(os.getenv("LOG_LEVEL", "INFO"))


def log_debug_attributes(obj: dict[str, Any]) -> None:
    """
    Log all accessible attributes of the given object at the debug level.

    Iterates over the attributes returned by `dir(obj)` and attempts to retrieve
    and log each attribute's value. If an attribute cannot be accessed (e.g., raises
    an AttributeError), logs the error with contextual information.

    :param obj: The object whose attributes will be logged.
    :type obj: dict[str, Any]
    """
    for attr in dir(obj):
        try:
            LOG.debug("obj.%s = %r", attr, getattr(obj, attr))
        except AttributeError as error:
            LOG.exception("Failed to access attribute '%s' of object of type '%s': %s", attr, type(obj).__name__, error)


def log_debug_json(content: dict[str, Any]) -> None:
    """
    Log a JSON-formatted dictionary at the debug level with pretty-printing.

    :param content: A dictionary representing JSON data to be logged.
    :type content: dict[str, Any]
    """
    LOG.debug(ujson.dumps(content, indent=4, escape_forward_slashes=False))
