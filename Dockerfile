FROM node:14-alpine as BUILD-FRONTEND

RUN apk add --update \
    && apk add --no-cache git\
    && rm -rf /var/cache/apk/*

RUN git clone https://github.com/CSCfi/metadata-submitter-frontend.git

WORKDIR /metadata-submitter-frontend
RUN npm install && npm run build

FROM python:3.7-alpine3.13 as BUILD-BACKEND

RUN apk add --update \
    && apk add --no-cache build-base curl-dev linux-headers bash git musl-dev libffi-dev \
    && apk add --no-cache python3-dev openssl-dev \
    && rm -rf /var/cache/apk/*

COPY requirements.txt /root/submitter/requirements.txt
COPY README.md /root/submitter/README.md
COPY setup.py /root/submitter/setup.py
COPY metadata_backend /root/submitter/metadata_backend
COPY --from=BUILD-FRONTEND /metadata-submitter-frontend/build \
    /root/submitter/metadata_backend/frontend

RUN apk add --no-cache rust cargo \
    && rm -rf /var/cache/apk/*

RUN pip install --upgrade pip && \
    pip install -r /root/submitter/requirements.txt && \
    pip install /root/submitter

FROM python:3.7-alpine3.13

RUN apk add --no-cache --update bash

LABEL maintainer="CSC Developers"
LABEL org.label-schema.schema-version="1.0"
LABEL org.label-schema.vcs-url="https://github.com/CSCfi/metadata-submitter"

COPY --from=BUILD-BACKEND /usr/local/lib/python3.7/ /usr/local/lib/python3.7/

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
