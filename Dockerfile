# N.B. The Python versions in the builder and prod images must match.
# Make sure to update *both* FROM lines when making changes!

ARG EDDYPRO_IMAGE=740991959481.dkr.ecr.eu-west-2.amazonaws.com/eddypro-engine:v0.1.5
FROM ${EDDYPRO_IMAGE} AS eddypro

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

ENV UV_PYTHON_INSTALL_DIR=/python UV_PYTHON_PREFERENCE=only-managed

RUN uv python install 3.12

RUN apt update && apt install -y --no-install-recommends git

WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=src/dritimeseriesprocessor/__init__.py,target=src/dritimeseriesprocessor/__init__.py \
    uv sync --locked --no-install-project --no-dev
COPY pyproject.toml uv.lock LICENSE README.md /app
COPY .git /app/.git
COPY src /app/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Build production container (no EddyPro)
FROM python:3.12-slim AS prod-base

COPY --from=builder --chown=python:python /python /python

# Copy the application from the builder
COPY --from=builder --chown=app:app /app /app

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH" VIRTUAL_ENV="/app/.venv"


# Build production container (with EddyPro)
FROM prod-base AS prod-eddypro

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    ca-certificates \
    libgfortran5 \
    p7zip-full \
    && rm -rf /var/lib/apt/lists/*

COPY --from=eddypro /opt/eddypro/bin /opt/eddypro/bin

# Ensure EddyPro executables are always on PATH
RUN ln -sf /opt/eddypro/bin/eddypro_rp /usr/local/bin/eddypro_rp \
    && ln -sf /opt/eddypro/bin/eddypro_fcc /usr/local/bin/eddypro_fcc

ENV PATH="/opt/eddypro/bin:/app/.venv/bin:$PATH" VIRTUAL_ENV="/app/.venv"

# Default target: production image with EddyPro
FROM prod-eddypro AS prod
