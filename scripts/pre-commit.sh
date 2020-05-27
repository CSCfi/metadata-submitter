#!/bin/sh

# Comment out pre-commit hooks you don't want to use

echo "Running tox as a pre-commit hook"
cd $(git rev-parse --show-toplevel) && tox

if [ $? -ne 0 ]; then
    echo "=============================="
    echo "Tests must pass before commit!"
    echo "Note: Tox also checks non-staged changes, so you might need to stash
    or add your changes before committing"
    exit 1
fi

echo "Running misspell as a pre-commit hook"
# Checking misspell against files and folder not in .gitignore
files=$(git ls-tree HEAD | awk '{print $4}' | tr '\n' ' ')
output=$(cd $(git rev-parse --show-toplevel) && misspell $files)

if [[ $output ]]; then
    echo "=============================="
    echo "Check your spelling errors before commit!"
    echo "You had following errors:"
    echo $output
    echo "To fix errors with one command, run: misspell -w $files"
    exit 1
fi
