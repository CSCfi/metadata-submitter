#!/bin/sh

THE_HOST=${HOST:="0.0.0.0"}
THE_PORT=${PORT:="5430"}

if [ -n "${SERVE_KEY}" ] && [ -r "${SERVE_KEY}" ]; then
    KF=--keyfile=${SERVE_KEY}
fi

if [ -n "${SERVE_CERT}" ] && [ -r "${SERVE_CERT}" ]; then
    CERT=--certfile=${SERVE_CERT}
fi

if [ -n "${SERVE_CA}" ] && [ -r "${SERVE_CA}" ]; then
    CA=--ca-certs=${SERVE_CA}
fi

if [ -n "${SERVE_SSLVERSION}" ]; then
    SSLVERSION=--ssl-version=${SERVE_SSLVERSION}
fi

if [ -n "${SERVE_CIPHERS}" ]; then
    CIPHERS=--ciphers=${SERVE_CIPHERS}
fi

if [ -n "${SERVE_CERTREQS}" ]; then
    CERTREQS=--cert-reqs=${SERVE_CERTREQS}
fi

if [ -n "$KF" ] && [ -z "$CERT" ]; then
    echo "Specified keyfile but not certificate, aborting."
    exit 1
fi

if [ -z "$KF" ] && [ -n "$CERT" ]; then
    echo "Specified certificate but not keyfile, aborting."
    exit 1
fi

if [ -n "$KF" ] && [ -n "$CERT" ]; then
  tlsconfig=1
fi


if [ -n "$SSLVERSION" ] || [ -n "$CERTREQS" ] || [ -n "$CIPHERS" ] || [ -n "$CA" ]; then
  if [ -z "$tlsconfig" ]; then
    echo "Some TLS configured but missing certificate or keyfile, aborting."
    exit 1
  fi
fi


echo 'Starting metadata backend'
# shellcheck disable=SC2086
exec gunicorn $KF $CERT $CA $SSLVERSION $CIPHERS $CERTREQS \
     --bind $THE_HOST:$THE_PORT \
     --worker-class aiohttp.GunicornUVLoopWebWorker \
     --workers 1 \
     --graceful-timeout 60 \
     --timeout 120 \
     metadata_backend.server:init
