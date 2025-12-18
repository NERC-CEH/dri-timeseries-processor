# Time Series Data Processing Pipeline

A pipeline for processing environmental time series data from monitoring networks. The system performs corrections, 
quality control, infilling, aggregation, and derivation operations on meteorological and hydrological measurements.

## Overview

This pipeline processes time series data through a metadata-driven approach:

1. **Fetches metadata** from the FDRI Metadata API to build a dependency graph of datasets
2. **Processes datasets** in topological order, ensuring dependencies are satisfied
3. **Applies operations** sequentially: corrections > quality control > infilling > aggregation/derivation
4. **Writes results** to S3 storage as partitioned parquet files

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
Formating uses ruff using the config in pyproject.toml which follows the default black settings.
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
VSCode has a useful test runner, allowing running and debugging of all tests within the repository. To allow VSCode to 
detect the tests, use the `Configure Tests` option accessed either via the help menu (select "Show All Commands" and 
type "Configure Tests" in the search bar), or via the test runner panel and select the "Configure Tests" button if 
it is available. To configure the tests, select `pytest` as the test runner framework and `testing` as the directory 
containing the tests.

### Pre commit hooks
Run below to setup the pre-commit hooks.
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


## CLI

The pipeline can be run from the command line, and supports two processing modes, selected via the first positional 
argument:

### 1. Explicit Mode

Fine-grained control over specific site/variable/periodicity combinations:

```bash
python -m new_processor explicit \
  --network cosmos \
  --lookback P2D \
  --selection ALIC1 TA PT30M \
  --selection BUNNY PA PT30M \
  --selection BUNNY PRECIP P1D
```

**Options:**
- `--selection SITE VARIABLE PERIODICITY` (repeatable)

### 2. Cross-Product Mode

Bulk processing across dimensions. Any omitted dimension processes all available values:

```bash
python -m new_processor cross-product \
  --network cosmos \
  --lookback P2D \
  --sites ALIC1 BUNNY \
  --variables TA PA \
  --periodicities PT30M P1D
```

**Options:**
- `--sites SITE1 SITE2 ...` (optional, defaults to all sites)
- `--variables VAR1 VAR2 ...` (optional, defaults to all variables)
- `--periodicities PER1 PER2 ...` (optional, defaults to all periodicities)

### Common Arguments

Both modes share these parameters:

- `--network {cosmos|fdri}` (required) - Network to process
- `--lookback DURATION` - ISO8601 duration from end-date (default: `P2D`)
  - Examples: `P1D` (1 day), `P1M` (1 month), `P1Y` (1 year)
  - Cannot contain time components (no `T` in duration)
- `--start-date YYYY-MM-DD` - Explicit start date (mutually exclusive with `--lookback`)
- `--end-date YYYY-MM-DD` - End date (default: today)

### Examples

**Process last 7 days for all COSMOS data:**
```bash
python -m new_processor cross-product --network cosmos --lookback P7D
```

**Process specific date range for temperature variable for all COSMOS sites:**
```bash
python -m new_processor cross-product \
  --network cosmos \
  --start-date 2024-01-01 \
  --end-date 2024-01-31 \
  --variables TA
```

**Process single dataset with explicit selection:**
```bash
python -m new_processor explicit \
  --network fdri \
  --lookback P1D \
  --selection HOLLN PA PT30M
```

## Pipeline flow

```
CLI Arguments
    ↓
Metadata API Query
    ↓
Dependency Graph Construction
    ↓
Topological Sorting
    ↓
For each dataset (in dependency order):
    ├─ Load Raw Data (if base dataset)
    ├─ Apply Corrections
    ├─ Apply Quality Control
    ├─ Apply Infilling
    ├─ Aggregate / Derive (if applicable)
    └─ Write to S3
```

## Adding New Processing Methods

All processing methods use a registry pattern with decorators. To add a new method:

### 1. Correction Example

```python
# In operations/correction/correction_methods.py

@CorrectionMethod.register
class MyCorrection(CorrectionMethod):
    name = "my_correction"
    flag_value = 64  # Next power of 2

    def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
        # Implement correction logic
        correction_factor = config.params["correction_factor"]
        # ... apply correction
        return tf
```

### 2. QC Check Example

```python
# In operations/quality_control/qc_methods.py

@QcMethod.register
class MyCheck(QcMethod):
    name = "my_check"
    flag_value = 1024  # Next power of 2

    def run(self, tf: ts.TimeFrame, config: MethodConfig) -> ts.TimeFrame:
        return tf.qc_check(
            "range",
            max_value=config.params["max"],
            min_value=config.params["min"],
            column_name=tf.metadata["column_name"],
        )
```

### 3. Derivation Example

```python
# In operations/derivation/derivation_methods.py

@DerivationMethod.register
class MyDerivation(DerivationMethod):
    name = "calculate-my_variable"
    inputs = ("input1", "input2")  # Required input TimeFrames

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        # Return Polars expression for calculation
        return columns["input1"] * columns["input2"]
```

Methods are automatically discovered and invoked based on metadata configurations.