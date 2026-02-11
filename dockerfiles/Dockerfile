#=======================
FROM ghcr.io/astral-sh/uv:python3.14-trixie AS build-backend
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
RUN uv sync

#=======================
FROM ghcr.io/astral-sh/uv:python3.14-trixie
#=======================

LABEL maintainer="CSC Developers"
LABEL org.label-schema.schema-version="1.0"
LABEL org.label-schema.vcs-url="https://github.com/CSCfi/metadata-submitter"

WORKDIR /app

COPY --from=BUILD-BACKEND /app .
COPY ./deploy/app.sh .
RUN chmod +x /app/app.sh

# https://manpages.debian.org/trixie/adduser/adduser.8.en.html
RUN adduser submitter

ENV PATH="/app/uv:$PATH"
USER submitter
ENTRYPOINT ["uv", "run", "metadata_submitter"]
