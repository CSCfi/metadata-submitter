#!/bin/sh

# Comment out pre-commit hooks you don't want to use

echo "Running tox as a pre-commit hook"
root_dir=$(git rev-parse --show-toplevel)

cd "$root_dir" || exit 1

if ! tox -r -p auto ; then
    echo "=============================="
    echo "Tests must pass before commit!"
    echo "Note: Tox also checks non-staged changes, so you might need to stash
    or add your changes before committing"
    exit 1
fi

if ! command -v pyspelling > /dev/null 2>&1; then
    echo "pyspelling not installed, not running as pre-commit hook"
    exit 0
elif ! aspell -v > /dev/null 2>&1; then
    echo "aspell is not installed, not running as pre-commit hook"
    exit 0
fi

echo "Running pyspelling as a pre-commit hook"
# Checking pyspelling against files and folder not in .gitignore

if ! pyspelling -v -c "$root_dir/.github/config/.spellcheck.yml"; then
    echo "=============================="
    echo "Check your spelling errors before commit!"
    echo "To fix errors with one command, run: pyspelling -v -c $root_dir/.github/config/.spellcheck.yml"
    exit 1
fi
