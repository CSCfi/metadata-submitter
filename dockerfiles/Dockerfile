#=======================
FROM ghcr.io/astral-sh/uv:0.12.10-python3.14-trixie-slim@sha256:d5ddd498c5a28ec77ff1c70276f8f3c4a116a303c8b5583a018ea43c2e89e366 AS build-backend
#=======================

WORKDIR /app

# Copy uv files
COPY pyproject.toml .
COPY uv.lock .
COPY .python-version .
COPY uv-artifactory.sh .

# Copy project files
COPY README.md .
COPY metadata_backend ./metadata_backend

RUN apt-get update && apt-get install -yqq git

# Install dependencies and create virtual environment
RUN --mount=type=secret,id=vault_secrets \
    ./uv-artifactory.sh uv sync --frozen

#=======================
FROM ghcr.io/astral-sh/uv:0.12.10-python3.14-trixie-slim@sha256:d5ddd498c5a28ec77ff1c70276f8f3c4a116a303c8b5583a018ea43c2e89e366
#=======================

LABEL maintainer="CSC Developers"
LABEL org.opencontainers.image.authors="CSC"
LABEL org.opencontainers.image.title="metadata-submitter"
LABEL org.opencontainers.image.description="SD Submit: sensitive data submission service"
LABEL org.opencontainers.image.source="https://github.com/CSCfi/metadata-submitter"
LABEL org.opencontainers.image.url="https://github.com/CSCfi/metadata-submitter"
LABEL org.opencontainers.image.licenses="MIT"

# Setup the working directory
WORKDIR /app

# To fix vulnerabilities
RUN apt-get update && apt-get install --only-upgrade -yqq perl-base libc6 libc-bin

# Add the user and group, and make it own /app
RUN groupadd -r -g 998 submitter \
  && useradd -r -g 998 -u 998  -m submitter \
  && chown -R 998:998 /app

# Copy the application
COPY --chown=998:998 --from=build-backend  /app .

# Copy the launcher
COPY --chown=998:998 ./deploy/app.sh /app/app.sh

# Setup the user and PATH
USER 998
ENV PATH="/app/uv:$PATH"

ENTRYPOINT ["/app/.venv/bin/metadata_submitter"]
