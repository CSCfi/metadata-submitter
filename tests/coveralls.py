#!/bin/env/python

import os
from subprocess import call
import sys

if __name__ == '__main__':
    if 'TRAVIS' in os.environ:
        rc = call('coveralls')
        sys.stdout.write("Coveralls report from TRAVIS CI.\n")
        raise SystemExit(rc)
    else:
        sys.stdout.write("Not on TRAVIS CI.\n")
