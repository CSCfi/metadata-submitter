#=======================
FROM node:20-alpine AS build-frontend
#=======================

RUN apk add --update \
    && apk add --no-cache git\
    && rm -rf /var/cache/apk/*

ARG BRANCH=main

RUN git clone -b ${BRANCH} https://github.com/CSCfi/metadata-submitter-frontend.git

WORKDIR /metadata-submitter-frontend

RUN corepack enable && corepack prepare pnpm@latest --activate

RUN pnpm install --prod --ignore-scripts && pnpm add -D vite-plugin-node-polyfills

RUN pnpm run build

#=======================
FROM python:3.13-alpine3.17 AS build-backend
#=======================

RUN apk add --update \
    && apk add --no-cache build-base curl-dev linux-headers bash git musl-dev libffi-dev \
    && apk add --no-cache python3-dev openssl-dev rust cargo libstdc++ curl \
    && rm -rf /var/cache/apk/*

WORKDIR /app

# Copy uv files
COPY pyproject.toml .
COPY uv.lock .
COPY .python-version .

# Copy project files
COPY README.md .
COPY metadata_backend ./metadata_backend
COPY scripts ./scripts
COPY docs/openapi.yml ./docs/openapi.yml
COPY --from=BUILD-FRONTEND /metadata-submitter-frontend/build \
    ./metadata_backend/frontend

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/app/uv" sh
ENV PATH="/app/uv:$PATH"

# Install dependencies and create virtual environment
RUN uv sync

# Generate OpenAPI docs.
RUN uv run scripts/swagger/generate.sh

#=======================
FROM python:3.13-alpine3.17
#=======================

RUN apk add --update \
    && apk add --no-cache libstdc++

LABEL maintainer="CSC Developers"
LABEL org.label-schema.schema-version="1.0"
LABEL org.label-schema.vcs-url="https://github.com/CSCfi/metadata-submitter"

WORKDIR /app

COPY --from=BUILD-BACKEND /app .
COPY ./deploy/app.sh .
RUN chmod +x /app/app.sh

RUN addgroup -g 1001 submitter && \
    adduser -D -u 1001 --disabled-password \
    --no-create-home -G submitter submitter

ENV PATH="/app/uv:$PATH"

ENTRYPOINT ["uv", "run", "/app/app.sh"]
