#!/usr/bin/env bash
git_root=$(git rev-parse --show-toplevel)

echo "Installing hooks..."
# this command creates symlink to our pre-commit script
ln -s $git_root/scripts/pre-commit.bash $git_root/.git/hooks/pre-commit
echo "Done!
