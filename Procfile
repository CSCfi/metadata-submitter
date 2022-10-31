db:             docker run -v ${PWD}/scripts/init_mongo.js:/docker-entrypoint-initdb.d/init_mongo.js:ro --env-file ${PWD}/.env -p 27017:27017 -p 28017:28017 mongo
messagebroker:  docker run -v ${PWD}/scripts/rabbitmq.conf:/etc/rabbitmq/rabbitmq.conf:ro -v ${PWD}/scripts/rabbitmq-definitions.json:/etc/rabbitmq/rabbitmq-definitions.json:ro -v mq:/var/lib/rabbitmq --env-file ${PWD}/.env -p 15672:15672 -p 5672:5672 rabbitmq:3.11.1-management-alpine
mockauth:   gunicorn --reload --worker-class aiohttp.GunicornUVLoopWebWorker --workers 1 --log-level debug --graceful-timeout 60 --timeout 120 --bind ${BACKEND_HOST}:8000              tests.integration.mock_auth:init
mockdoi:    gunicorn --reload --worker-class aiohttp.GunicornUVLoopWebWorker --workers 1 --log-level debug --graceful-timeout 60 --timeout 120 --bind ${BACKEND_HOST}:8001              tests.integration.mock_doi_api:init
mockmetax:  gunicorn --reload --worker-class aiohttp.GunicornUVLoopWebWorker --workers 1 --log-level debug --graceful-timeout 60 --timeout 120 --bind ${BACKEND_HOST}:8002              tests.integration.mock_metax_api:init
mockrems:   gunicorn --reload --worker-class aiohttp.GunicornUVLoopWebWorker --workers 1 --log-level debug --graceful-timeout 60 --timeout 120 --bind ${BACKEND_HOST}:8003              tests.integration.mock_rems_api:init
backend:    gunicorn --reload --worker-class aiohttp.GunicornUVLoopWebWorker --workers 1 --log-level debug --graceful-timeout 60 --timeout 120 --bind ${BACKEND_HOST}:${BACKEND_PORT}   metadata_backend.server:init
