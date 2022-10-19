#!/bin/sh

if [ -n "$BROKER_VHOST" ] || [ -n "$BROKER_EXCHANGE" ] || [ -n "$BROKER_QUEUE" ] ; then
    echo "Some MQ Consumer configuration is missing, aborting."
    exit 1
fi

echo 'Starting consumer for metadata'
# shellcheck disable=SC2086
exec metadata_backend.consumer:init
