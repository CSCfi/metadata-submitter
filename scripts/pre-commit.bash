#!/usr/bin/env bash

echo "Running tox as pre-commit hook"
cd $(git rev-parse --show-toplevel) && tox

# $? stores exit value of the last command
if [ $? -ne 0 ]; then
    echo "=============================="
    echo "Tests must pass before commit!"
    echo "Note: Tox also checks non-staged changes, so you might need to stash
    your changes before commiting"
    exit 1
fi
