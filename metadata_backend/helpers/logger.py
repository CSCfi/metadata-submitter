"""Logging formatting and functions for debugging"""

import logging

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
