#=======================
FROM ghcr.io/astral-sh/uv:python3.14-trixie@sha256:a8433b4080bfc7d63c803189f90a026acb9b2c8d9a003868236194a839da9a6c AS build-backend
#=======================

WORKDIR /app

# Copy uv files
COPY pyproject.toml .
COPY uv.lock .
COPY .python-version .

# Copy project files
COPY README.md .
COPY metadata_backend ./metadata_backend

# Install dependencies and create virtual environment
RUN uv sync --frozen

#=======================
FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim@sha256:0e664b12a6be9cd16be1015ec5cc3feebdeb42078ab587389707afbdfab8b10f
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
