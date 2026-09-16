#!/bin/sh
set -e

if [ -f /run/secrets/vault_secrets ]; then
  grep '^UV_' /run/secrets/vault_secrets > /tmp/uv_env
  set -a && . /tmp/uv_env && set +a
fi

exec "$@"
