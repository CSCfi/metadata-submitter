FROM python:3.7-alpine3.9 as BUILD

RUN apk add --update \
    && apk add --no-cache build-base curl-dev linux-headers bash git musl-dev\
    && rm -rf /var/cache/apk/*

COPY requirements.txt /root/submitter/requirements.txt
COPY README.md /root/submitter/README.md
COPY setup.py /root/submitter/setup.py
COPY metadata_backend /root/submitter/metadata_backend

RUN pip install --upgrade pip && \
    pip install -r /root/submitter/requirements.txt && \
    pip install /root/submitter

FROM python:3.7-alpine3.9

RUN apk add --no-cache --update bash

LABEL maintainer="otahontas"
LABEL org.label-schema.schema-version="1.0"
LABEL org.label-schema.vcs-url="https://github.com/CSCfi/metadata_submitter"

COPY --from=BUILD /usr/local/lib/python3.7/ /usr/local/lib/python3.7/

COPY --from=BUILD /usr/local/bin/gunicorn /usr/local/bin/

COPY --from=BUILD /usr/local/bin/submitter /usr/local/bin/

RUN mkdir -p /app

WORKDIR /app

COPY ./deploy/app.sh /app/app.sh

RUN chmod +x /app/app.sh

ENTRYPOINT ["/bin/sh", "-c", "/app/app.sh"]
