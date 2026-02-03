# N.B. The Python versions in the builder and prod images must match.
# Make sure to update *both* FROM lines when making changes!

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
COPY pyproject.toml uv.lock /app
COPY .git /app/.git
COPY src /app/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Build production container
FROM python:3.12-slim AS prod

COPY --from=builder --chown=python:python /python /python

# Copy the application from the builder
COPY --from=builder --chown=app:app /app /app

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH" VIRTUAL_ENV="/app/.venv"

# Unsetting entrypoint from parent image
ENTRYPOINT []

CMD ["python", "-m", "dritimeseriesprocessor", "from-cross-product", "--network", "cosmos", "--sites", "cosmos-alic1",  "cosmos-bunny", "--periodicities", "PT30M", "--variables", "TA",  "PA",  "WS",  "WD", "--start-date", "2025-08-10", "--end-date", "2026-02-02"]
