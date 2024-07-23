FROM python:3.12-slim


COPY src /app/src/

# Needed for autosemver to work
COPY .git /app/.git/

COPY pyproject.toml /app/

WORKDIR /app

RUN pip install .
