mockldap:       docker build -f ${PWD}/dockerfiles/Dockerfile-ldap-dev -t ldap . && docker run --rm -p 389:389 --name mock-ldap ldap
mock-s3:        docker run --rm -p 8006:8006 --env MOTO_PORT=8006 --name mock-s3 motoserver/moto:latest
mockkeystone:   docker run --rm -p 5001:5001 --env S6_LOGGING=0 --name keystone-swift ghcr.io/cscfi/docker-keystone-swift:latest
mockauth:       gunicorn --reload --worker-class aiohttp.GunicornUVLoopWebWorker --workers 1 --log-level debug --graceful-timeout 60 --timeout 120 --bind ${BACKEND_HOST}:8000              tests.integration.mock_auth:init
mockdatacite:   gunicorn --reload --worker-class aiohttp.GunicornUVLoopWebWorker --workers 1 --log-level debug --graceful-timeout 60 --timeout 120 --bind ${BACKEND_HOST}:8001              tests.integration.mock_datacite_api:init
mockmetax:      gunicorn --reload --worker-class aiohttp.GunicornUVLoopWebWorker --workers 1 --log-level debug --graceful-timeout 60 --timeout 120 --bind ${BACKEND_HOST}:8002              tests.integration.mock_metax_api:init
mockrems:       gunicorn --reload --worker-class aiohttp.GunicornUVLoopWebWorker --workers 1 --log-level debug --graceful-timeout 60 --timeout 120 --bind ${BACKEND_HOST}:8003              tests.integration.mock_rems_api:init
mockadmin:      gunicorn --reload --worker-class aiohttp.GunicornUVLoopWebWorker --workers 1 --log-level debug --graceful-timeout 60 --timeout 120 --bind ${BACKEND_HOST}:8004              tests.integration.mock_admin_api:init
mockpid:        gunicorn --reload --worker-class aiohttp.GunicornUVLoopWebWorker --workers 1 --log-level debug --graceful-timeout 60 --timeout 120 --bind ${BACKEND_HOST}:8005              tests.integration.mock_pid_api:init
backend:        gunicorn --reload --worker-class aiohttp.GunicornUVLoopWebWorker --workers 1 --log-level debug --graceful-timeout 60 --timeout 120 --bind ${BACKEND_HOST}:5430              metadata_backend.server:init
