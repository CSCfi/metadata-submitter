"""Logging formatting and functions for debugging."""

import logging
import os
from typing import Dict

import ujson

FORMAT = (
    "[%(asctime)s][%(name)s][%(process)d %(processName)s] [%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
)
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

LOG = logging.getLogger("server")
LOG.setLevel(os.getenv("LOG_LEVEL", "INFO"))


def get_attributes(obj: Dict) -> None:
    """Print all attributes of given object.

    :param obj: Any kind of object
    """
    for attr in dir(obj):
        try:
            LOG.info("obj.%s = %r", attr, getattr(obj, attr))
        except AttributeError as error:
            LOG.info("Error: %r", error)


def pprint_json(content: Dict) -> None:
    """Print given JSON object to LOG.

    :param content: JSON-formatted content to be printed
    """
    LOG.info(ujson.dumps(content, indent=4, escape_forward_slashes=False))
