"""Logging formatting and functions for debugging."""

import logging
import os

FORMAT = "[{asctime}][{name}][{process} {processName:<12}] [{levelname:8s}](L:{lineno}) {funcName}: {message}"
logging.basicConfig(format=FORMAT, datefmt="%Y-%m-%d %H:%M:%S", style="{")

LOG = logging.getLogger("server")
LOG.setLevel(os.getenv("LOG_LEVEL", "INFO"))
