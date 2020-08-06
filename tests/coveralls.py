#!/bin/env/python

"""Coveralls settings for travis and local usage."""

import os
import sys
from subprocess import call

if __name__ == "__main__":
    if "COVERALLS_REPO_TOKEN" in os.environ:
        rc = call("coveralls")
        sys.stdout.write("Coveralls report from Github Actions.\n")
        raise SystemExit(rc)
    else:
        sys.stdout.write("Not on Github Actions.\n")
