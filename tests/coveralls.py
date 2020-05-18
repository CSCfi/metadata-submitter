#!/bin/env/python

"""Coveralls settings for travis and local usage."""

import os
import sys
from subprocess import call

if __name__ == '__main__':
    if 'TRAVIS' in os.environ:
        rc = call('coveralls')
        sys.stdout.write("Coveralls report from TRAVIS CI.\n")
        raise SystemExit(rc)
    else:
        sys.stdout.write("Not on TRAVIS CI.\n")
