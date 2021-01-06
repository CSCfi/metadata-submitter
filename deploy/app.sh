#!/bin/sh 
THE_HOST=${HOST:="0.0.0.0"}
THE_PORT=${PORT:="5430"}

echo 'Start metadata backend'
exec gunicorn metadata_backend.server:init --bind $THE_HOST:$THE_PORT --worker-class aiohttp.GunicornUVLoopWebWorker --workers 1 --graceful-timeout 60 --timeout 120
