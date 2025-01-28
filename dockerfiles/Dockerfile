#=======================
FROM node:20-alpine AS BUILD-FRONTEND
#=======================

RUN apk add --update \
    && apk add --no-cache git\
    && rm -rf /var/cache/apk/*

ARG BRANCH=master

RUN git clone -b ${BRANCH} https://github.com/CSCfi/metadata-submitter-frontend.git

WORKDIR /metadata-submitter-frontend
RUN npx --quiet pinst --disable \
    && pnpm install --prod \
    && pnpm run build --prod

#=======================
FROM python:3.12-alpine3.17 AS BUILD-BACKEND
#=======================

RUN apk add --update \
    && apk add --no-cache build-base curl-dev linux-headers bash git musl-dev libffi-dev \
    && apk add --no-cache python3-dev openssl-dev rust cargo libstdc++ \
    && rm -rf /var/cache/apk/*

COPY requirements.txt /root/submitter/requirements.txt
COPY README.md /root/submitter/README.md
COPY pyproject.toml /root/submitter/pyproject.toml
COPY metadata_backend /root/submitter/metadata_backend
COPY scripts /root/submitter/scripts
COPY docs/openapi.yml /root/submitter/docs/openapi.yml

COPY --from=BUILD-FRONTEND /metadata-submitter-frontend/build \
    /root/submitter/metadata_backend/frontend

RUN pip install --upgrade pip pyyaml && \
    ./root/submitter/scripts/swagger/generate.sh && \
    pip install /root/submitter

#=======================
FROM python:3.12-alpine3.17
#=======================

RUN apk add --update \
    && apk add --no-cache libstdc++

LABEL maintainer="CSC Developers"
LABEL org.label-schema.schema-version="1.0"
LABEL org.label-schema.vcs-url="https://github.com/CSCfi/metadata-submitter"

COPY --from=BUILD-BACKEND /usr/local/lib/python3.12/ /usr/local/lib/python3.12/

COPY --from=BUILD-BACKEND /usr/local/bin/gunicorn /usr/local/bin/

COPY --from=BUILD-BACKEND /usr/local/bin/metadata_submitter /usr/local/bin/

RUN mkdir -p /app

WORKDIR /app

COPY ./deploy/app.sh /app/app.sh

RUN chmod +x /app/app.sh

RUN addgroup -g 1001 submitter && \
    adduser -D -u 1001 --disabled-password \
    --no-create-home -G submitter submitter

ENTRYPOINT ["/bin/sh", "-c", "/app/app.sh"]
