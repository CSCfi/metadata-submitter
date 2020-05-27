#!/bin/sh
# Install pre-commit hook by running ./install-hooks.sh
git_root=$(git rev-parse --show-toplevel)
ln -s $git_root/scripts/pre-commit.sh $git_root/.git/hooks/pre-commit
echo "Symlinked pre-commit hook!"
