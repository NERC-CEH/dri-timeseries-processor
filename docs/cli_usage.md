# CLI Usage

The Time Series Processor includes a command-line interface (CLI) used to launch processing runs locally or via
workflow automation.

This document describes the CLI arguments, usage patterns, and operational behaviour.

## Running the Processor

The processor CLI is invoked using:

```console
 python -m dritimeseriesprocessor ...
```

The CLI accepts arguments defining:

 - **what** datasets to process
 - **over what time period**
 - **for which network** (not required for `from-datasets`)

## Processing Modes

The CLI supports three dataset selection modes and one utility command:

1. **explicit** (`from-selection`): Request datasets by site, variable, and periodicity.
2. **cross-product** (`from-cross-product`): Build dataset combinations across dimensions.
3. **from-datasets** (`from-datasets`): Request datasets directly by their metadata API ID.
4. **list-sites**: List all active sites for a network.

The processing modes are **mutually exclusive**.

### Explicit Mode

Fine-grained control over specific site/variable/periodicity combinations.

**Use when you need**:

* Exact control over which datasets to process
* Different periodicities for different sites
* Specific variable combinations per site

**Syntax**:

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

This processes:

* cosmos-alic1 site: Temperature (TA) at 30-minute resolution
* cosmos-bunny site: Air pressure (PA) at 30-minute resolution
* cosmos-bunny site: Precipitation (PRECIP) at daily resolution

### Cross-Product Mode

Bulk processing across dimensions. Omitted dimensions process all available values.

**Use when you need**:

* Same variables across multiple sites
* All combinations of sites and variables
* Bulk reprocessing operations

**Syntax**:

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

This processes **all combinations**: 

* cosmos-alic1 + TA + PT30M
* cosmos-alic1 + PA + PT30M
* cosmos-bunny + TA + PT30M
* cosmos-bunny + PA + PT30M

**Omitting dimensions**:

```bash
# Process ALL sites, ALL variables, ALL periodicities
python -m dritimeseriesprocessor cross-product --network cosmos --lookback P7D

# Process ALL sites for specific variables
python -m dritimeseriesprocessor cross-product
  --network cosmos 
  --lookback P7D 
  --variables TA PA
```

### From-Datasets Mode

Request one or more datasets directly by their metadata API ID. Works for both `TimeSeriesDataset` and
`ObservationDataset` records - the dataset type does not need to be known in advance.

This mode does not require `--network` because the dataset ID is self-contained.

**Use when you need**:

* To process a specific named dataset (e.g. a flux observation bundle)
* To trigger processing without knowing a dataset's site or variable dimensions
* To process datasets of different types in a single run

**Syntax**:

```bash
python -m dritimeseriesprocessor from-datasets
  [--lookback DURATION | --start-date YYYY-MM-DD]
  [--end-date YYYY-MM-DD]
  --datasets DATASET_ID [DATASET_ID2 ...]
```

**Example**:

```bash
python -m dritimeseriesprocessor from-datasets \
  --datasets flux-plynl-processed \
  --start-date 2024-08-14 \
  --end-date 2024-08-15
```

Multiple datasets can be listed together:

```bash
python -m dritimeseriesprocessor from-datasets \
  --datasets flux-site1-processed flux-site2-processed \
  --lookback P7D
```

### List-Sites Mode

Outputs a JSON array of active site IDs for a given network to `/tmp/sites.json`. Sites whose operating period does
not overlap the requested date window are excluded.

Intended for use in Argo Workflows fan-out steps, where the output is captured as a step result and passed as input
to downstream processing steps.

**Syntax**:

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

This writes to `/tmp/sites.json`:

```json
["cosmos-alic1", "cosmos-bunny", "cosmos-eustn"]
```

### Site Names

Uses the site IDs as found in the FDRI metadata API.  These are typically in the form `<network>-<site-id>`, but
theoretically could be anything.

**Examples:**

- `cosmos-alic1` - Alice Holt in the COSMOS network
- `cosmos-bunny` - Bunny Park in the COSMOS network
- `fdri-se-carwe-01` - Carreg Wen in the FDRI network

### Variable Names

Uses the variable IDs as found in the `sourceColumnName` field within the FDRI metadata API datasets end point.
These are specific for any given site (though typically all sites in a network will have the same column names).

**Examples (for COSMOS network):**

- `TA` - Air temperature
- `PA` - Air pressure
- `RH` - Relative humidity
- `WS` - Wind speed
- `WD` - Wind direction
- `PRECIP` - Precipitation
- `SWIN` - Incoming shortwave radiation
- `SWOUT` - Outgoing shortwave radiation
- `LWIN` - Incoming longwave radiation
- `LWOUT` - Outgoing longwave radiation
- `RN` - Net radiation
- `PE` - Potential evapotranspiration

### Periodicity Values

Common periodicities (ISO8601 duration format):

* `PT30M` - 30 minutes
* `PT1H` - 1 hour
* `P1D` - 1 day

## Core Arguments

All modes share the date range arguments. Network is shared by all modes except `from-datasets`.

### Network Selection

Required for `from-selection`, `from-cross-product`, and `list-sites`. Not used by `from-datasets`.

```bash
--network {cosmos|fdri}
```

### Date Range Selection

Choose one of two methods to specify the date range:

#### Method 1: Lookback Duration (default)

Process data going backward from the end date:

```bash
--lookback DURATION
```

* Default: `P2D` (2 days)
* Format: ISO8601 duration
* Cannot contain time components (no hours/minutes)

Valid examples:

* `P1D` - 1 day
* `P7D` - 7 days (1 week)
* `P1M` - 1 month
* `P1Y` - 1 year

Invalid examples:

* `PT6H` - Invalid (contains time component)

#### Method 2: Explicit Start Date

Specify an exact start date (mutually exclusive with `--lookback`):

```bash
--start-date YYYY-MM-DD
```

### End Date

Optional. Defaults to today:

```bash
--end-date YYYY-MM-DD
```

## Error Handling

#### Invalid Arguments

The CLI validates all arguments before processing. Examples include:

```bash
# Invalid: Missing required network
python -m dritimeseriesprocessor cross-product --lookback P2D

# Invalid: Time component in lookback
python -m dritimeseriesprocessor cross-product --network cosmos --lookback PT6H

# Invalid: Both lookback and start-date
python -m dritimeseriesprocessor cross-product
  --network cosmos 
  --lookback P2D 
  --start-date 2024-01-01
```
