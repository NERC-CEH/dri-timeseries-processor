# Time Series Data Processing Pipeline

A pipeline for processing environmental time series data from monitoring networks. The system performs corrections, 
quality control, infilling, aggregation, and derivation operations on meteorological and hydrological measurements.

## Overview

This pipeline processes time series data through a metadata-driven approach:

1. **Fetches metadata** from the FDRI Metadata API to build a dependency graph of datasets
2. **Processes datasets** in topological order, ensuring dependencies are satisfied
3. **Applies operations** corrections > quality control > infilling > aggregation/derivation
4. **Writes results** to S3 storage as partitioned parquet files

## Basic usage

The processor CLI is invoked using:

```bash
python -m dritimeseriesprocessor ... 
```

Use one of two (mutually exclusive) processing modes, or the utility command:

1. Explicit: `from-selection`
    - Individual sets of processing arguments

    ```bash
    python -m dritimeseriesprocessor from-selection
     --network NETWORK
     [--lookback DURATION | --start-date YYYY-MM-DD]
     [--end-date YYYY-MM-DD]
     --selection SITE VARIABLE PERIODICITY
     [--selection SITE2 VARIABLE2 PERIODICITY2 ...]
    ```

    **Example**:

    ```bash
    python -m dritimeseriesprocessor from-selection
     --network cosmos
     --lookback P2D
     --selection cosmos-alic1 TA PT30M
     --selection cosmos-bunny PA PT30M
     --selection cosmos-bunny PRECIP P1D
    ```

2. Cross-product: `from-cross-product`
    - Bulk processing across processing dimensions

    ```bash
    python -m dritimeseriesprocessor from-cross-product
     --network NETWORK
     [--lookback DURATION | --start-date YYYY-MM-DD]
     [--end-date YYYY-MM-DD]
     [--sites SITE1 SITE2 ...]
     [--variables VAR1 VAR2 ...]
     [--periodicities PER1 PER2 ...]
    ```

    **Example**:

    ```bash
    python -m dritimeseriesprocessor from-cross-product
     --network cosmos
     --lookback P2D
     --sites cosmos-alic1 cosmos-bunny
     --variables TA PA
     --periodicities PT30M
    ```

3. List sites: `list-sites`
    - Writes a JSON array of active site IDs for a network to `/tmp/sites.json`
    - Sites not open during the requested date window are excluded

    ```bash
    python -m dritimeseriesprocessor list-sites
     --network NETWORK
     [--lookback DURATION | --start-date YYYY-MM-DD]
     [--end-date YYYY-MM-DD]
    ```

    **Example**:

    ```bash
    python -m dritimeseriesprocessor list-sites --network cosmos --lookback P2D
    ```

See [CLI Usage](docs/cli_usage.md) for more info.

## Developer Setup

This is for active development on the processing package itself.

### Requirements

#### Install uv

[Official instructions](https://docs.astral.sh/uv/getting-started/installation/)

### Clone the repository

```bash
git clone https://github.com/NERC-CEH/dri-timeseries-processor.git
cd dri-timeseries-processor
```

### Setting up and activating a virtual environment

```commandline
uv sync
source .venv/bin/activate
```

### Docker Compose

Build the Docker container to set up LocalStack (local AWS services):

```bash
docker compose up -d
```

This initialises:
- LocalStack S3 buckets with sample data
- Prometheus Pushgateway for metrics (accessible at `localhost:9091`)

### Linting
Linting uses ruff using the config in pyproject.toml
```
ruff check --fix
```

### Formatting
Formatting uses ruff using the config in pyproject.toml which follows the default black settings.
```
ruff format .
```

### Testing
Testing is done using pytest and tests are in the /tests directory.
```
pytest
```

Test data is automatically loaded into LocalStack S3 on container initialization.

#### Detecting tests using VSCode
VSCode has a useful test runner, allowing running and debugging of all tests within the repository. To allow VSCode to detect the tests, use the `Configure Tests` option accessed either via the help menu (select "Show All Commands" and type "Configure Tests" in the search bar), or via the test runner panel and select the "Configure Tests" button if it is available. To configure the tests, select `pytest` as the test runner framework and `testing` as the directory containing the tests.

### Pre commit hooks
Run below to set up the pre-commit hooks.
```
git config --local core.hooksPath .githooks/
```
This will set this repo up to use the git hooks in the `.githooks/` directory.
The hook runs `ruff format --check` and `ruff check` to prevent commits that are not formatted correctly or have errors.
The hook intentionally does not alter the files, but informs the user which command to run.

## Configuration

Configuration is environment-aware, loading from different sources based on the `environment` variable:

- **Local**: `__assets__/env.cfg` file
- **Staging/Production**: Environment variables directly

Required configuration keys:
- `AWS_DEFAULT_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- `level_0_bucket`, `processed_bucket`
- `metadata_api_url`
- `endpoint_url` (LocalStack only)

## Metrics

The pipeline exports Prometheus metrics to a Pushgateway:

- **Pipeline timing**: Total runtime, per-operation timings
- **Success/failure counts**: Datasets processed successfully or failed
- **Data availability**: Datasets with no data available

Locally accessible at `http://localhost:9091`

## Documentation

Available in [docs folder](docs/index.md).
