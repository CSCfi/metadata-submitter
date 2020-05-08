"""Logging formatting and functions for debugging"""

import logging
import json

FORMAT = "[%(asctime)s][%(name)s][%(process)d %(processName)s]" \
         "[%(levelname)-8s](L:%(lineno)s) %(funcName)s: %(message)s"
logging.basicConfig(format=FORMAT, datefmt='%Y-%m-%d %H:%M:%S')

LOG = logging.getLogger("server")
LOG.setLevel(logging.INFO)


def get_attributes(obj):
    """
    Prints all attributes of given object
    @param obj: Any object
    """
    for attr in dir(obj):
        try:
            LOG.info("obj.%s = %r" % (attr, getattr(obj, attr)))
        except AttributeError as error:
            LOG.info("Error: ", error)


def pprint_json(content):
    """
    Prints given json object to LOG
    @param content: json-formatted content to be printed
    """
    LOG.info(json.dumps(content, indent=4))
