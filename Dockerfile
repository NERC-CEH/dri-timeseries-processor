# Build virtualenv
FROM amazon/aws-lambda-python:3.12 as build
WORKDIR /app
COPY pyproject.toml README.md /app/
COPY src /app/src
COPY .git /app/.git
RUN pip install --upgrade pip pdm

RUN dnf install -y git

# Installs the codebase in editable mode into .venv
RUN pdm install

# Build production containerdocker
# Only the ./.venv ./src ./tests are present in the production image
FROM amazon/aws-lambda-python:3.12 as prod
ENV PATH="/app/.venv/bin:/usr/sbin:$PATH"
WORKDIR /app
RUN dnf install -y shadow-utils
RUN groupadd -g 999 python && \
    useradd -m -r -u 999 -g python python
RUN chown python:python /app
COPY --chown=python:python --from=build /app/.venv /app/.venv
COPY --chown=python:python --from=build /app/src /app/src
COPY --chown=python:python tests/ /app/tests

USER python
ENV VIRTUAL_ENV="/app/.venv"

# Unsetting entrypoint from parent image
ENTRYPOINT []

CMD ["python", "-m", "dritimeseriesprocessor", "P2D"]