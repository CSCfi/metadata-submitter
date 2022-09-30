"""Logging formatting and functions for debugging."""

import logging
import os
from typing import Dict

import ujson

FORMAT = "[{asctime}][{name}][{process} {processName:<12}] [{levelname:8s}](L:{lineno}) {funcName}: {message}"
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S", style="{")

LOG = logging.getLogger("server")
LOG.setLevel(os.getenv("LOG_LEVEL", "INFO"))


def get_attributes(obj: Dict) -> None:
    """Print all attributes of given object.

    :param obj: Any kind of object
    """
    for attr in dir(obj):
        try:
            LOG.debug("obj.%s = %r", attr, getattr(obj, attr))
        except AttributeError as error:
            LOG.exception("Error: %r", error)


def pprint_json(content: Dict) -> None:
    """Print given JSON object to LOG.

    :param content: JSON-formatted content to be printed
    """
    LOG.debug(ujson.dumps(content, indent=4, escape_forward_slashes=False))
