# Operations

Operations are the core execution units that perform data transformations during processing. Each operation implements
one specific functional behaviour applied to a `TimeFrame` and returning a modified `TimeFrame`.

## How operations are run

Operations are not run in a fixed order. Each dataset has a **plan** - an ordered list of data processing
configurations - and the pipeline runs the operations in the order the plan defines. See
[Architecture: The processing plan](architecture.md#the-processing-plan) for how the plan is built and iterated.

Each configuration has a type (`ConfigurationType`) that selects the operation to run: `CORRECTION`,
`QUALITY_CONTROL`, `INFILLING`, `AGGREGATION`, `DERIVATION` or `LOAD`. A type can appear more than once in a plan.

Most operations share a common workflow defined in `OperationPipeline`: initialise the flag system and flag column if
needed, apply each method in the configuration, then update the core flags. The exception is `LoadPipeline`, which
loads data into the container rather than transforming an existing `TimeFrame`.

## Corrections

Corrections adjust raw measurements for known systematic errors such as incorrect calibration, sensor drift, or
installation issues.

Correction behaviour is defined by metadata, which specifies:

- the correction method name (e.g., `add`, `scalar`, `power`)
- optional method parameters (e.g., numeric constants)
- valid date ranges for application
- dependent datasets (e.g., `UX` and `UY` for wind direction)
- required site attributes (e.g., altitude, latitude)

### Correction Methods

All correction methods are registered in `operations/correction/correction_methods.py`.

```python
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

## Quality Control (QC)

Quality control tests identify values that are invalid or  erroneous. QC does not change values - it flags them.

QC behaviour is defined by metadata, which specifies:

- the QC method name (e.g., `range`, `spike`, `comparison`)
- parameters such as thresholds or comparison types
- optional time filters (e.g., only apply at night)
- optional dependent datasets (e.g., battery voltage checks)
- optional site attributes or static constants

### QC Methods

All QC methods are registered in `operations/quality_control/qc_methods.py`.

```python
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

## Infilling

Infilling replaces missing or removed data values to produce a complete time series. Infilling may reference
properties within the same dataset or draw values from related datasets.

Infilling behaviour is defined by metadata, which specifies:

- the infilling method name (e.g., `linear`, `alt_data`)
- optional gap constraints (e.g., max gap length)
- optional priority rules for multiple infill strategies
- optional dependent datasets (e.g., use another sensor’s value)

### Infilling Methods

All infilling methods are registered in `operations/infill/infill_methods.py`.

```python
 @InfillingMethod.register
 class MyInterpolation(InfillingMethod):
     name = "my_infill"
     flag_value = 8  # Next power of 2

     def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
         # Implement interpolation logic
         # ... insert values for missing data
         return tf
```

## Aggregation

Aggregation resamples data into new temporal resolutions (e.g., 30-minute to daily) by combining multiple values
with a method such as a sum or mean.

Aggregation behaviour is defined by metadata, which specifies:

- the aggregation method name (e.g., `sum`, `mean`, `min`, `max`)
- the input dataset to aggregate
- the output resolution to compute

### Aggregation Methods

All aggregation methods are registered in `operations/aggregation/aggregation_methods.py`.
These typically use built-in `time-stream` aggregation functions.

```python
 @AggregationMethod.register
 class MyAggregation(AggregationMethod):
     name = "my_agg"

     def run(self, tf: ts.TimeFrame, config: ProcessingMethodConfig) -> ts.TimeFrame:
         # Implement aggregation logic
         # ... convert values to target resolution
         return tf
```

## Derivation

Derivation calculates new data values using existing datasets. Derived values represent measurements that are not
directly recorded.

Derivation behaviour is defined by metadata, which specifies:

- the derivation method name (e.g., `calculate_rn`, `calculate_pe`)
- required input datasets (e.g., SWIN, SWOUT, LWIN, LWOUT)
- optional site attributes or physical constants
- optional dependent parameters

### Derivation Methods

All derivation methods are registered in `operations/derivation/derivation_methods.py`
and implemented using specialised calculation classes.

```python
 @DerivationMethod.register
 class MyDerivation(DerivationMethod):
     name = "calculate-my_variable"
     inputs = ("input1", "input2")  # Required input TimeFrames

     def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
         # Return Polars expression for calculation
         return columns["input1"] * columns["input2"]
```
