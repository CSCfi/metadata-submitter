#!/bin/bash -x

CONTAINER=$1
WAITFOR=$2

MAXWAIT=60
count=0
until docker logs "$CONTAINER" 2>&1 | strings | grep "$WAITFOR"; do
  sleep 8
  if [ "$MAXWAIT" -eq "$count" ]; then
    exit 1
  fi
  count=$((count+1))
done
