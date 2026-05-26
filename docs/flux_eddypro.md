# Flux / EddyPro

EddyPro flux processing runs through the standard pipeline as a derivation step, triggered by requesting a flux
`ObservationDataset` via the `from-datasets` CLI mode.

## How it works

1. The `from-datasets` CLI mode accepts one or more dataset IDs directly. For flux, this is the ID of the processed
   observation dataset (e.g. `flux-plynl-processed`).

2. The dependency graph resolves the raw `.dat` input dataset as a `LOAD_LOCAL_COPY` dependency of the processed
   dataset.

3. During the `LOAD_LOCAL_COPY` step, `S3DataRouter.stage_locally` downloads the raw `.dat` files for the requested
   date range from S3 into a local temporary directory. The path is recorded on the raw dataset's `staged_dir`.

4. When the processed dataset's `DERIVATION` step runs, `EddyProRun` reads `staged_dir` from the raw dependency,
   builds EddyPro config files from templates, runs `eddypro_rp` and `eddypro_fcc`, and parses the output back into
   a `TimeFrame`.

5. The result is written to the processed S3 bucket in the normal way.

## Relevant code

- CLI parsing: `src/dritimeseriesprocessor/cli/cli.py` (`from-datasets` mode)
- App entrypoint: `src/dritimeseriesprocessor/app/run.py`
- Raw file staging: `src/dritimeseriesprocessor/routers/data/data_router.py` (`S3DataRouter.stage_locally`)
- EddyPro derivation method: `src/dritimeseriesprocessor/operations/derivation/derivation_methods.py` (`EddyProRun`)
- EddyPro config builder and runner: `src/dritimeseriesprocessor/operations/eddypro/`
- EddyPro config templates: `src/dritimeseriesprocessor/__assets__/eddypro_templates/`

## Requirements

- LocalStack running for S3 (local development)
- Local config pointing at LocalStack in `src/dritimeseriesprocessor/__assets__/env.cfg`
- `eddypro_rp` and `eddypro_fcc` available on `PATH`

If you run inside the project container, the binaries may already be present. If you run on your host machine, your
host still needs access to them.

## Expected S3 layout

Raw `.dat` files are read from the ingested bucket, partitioned by date:

```
<network>/dataset=<RAW_DATASET>/site=<SITE>/date=YYYY-MM-DD/
```

Outputs are written to the processed bucket under the same partition scheme:

```
<network>/dataset=<PROCESSED_DATASET>/site=<SITE>/date=YYYY-MM-DD/
```

## Running it

Pass the processed dataset ID to `from-datasets`:

```bash
python -m dritimeseriesprocessor from-datasets \
  --datasets flux-plynl-processed \
  --start-date 2024-08-14 \
  --end-date 2024-08-15
```

Multiple sites can be processed in one run by listing additional dataset IDs:

```bash
python -m dritimeseriesprocessor from-datasets \
  --datasets flux-site1-processed flux-site2-processed \
  --start-date 2024-08-14 \
  --end-date 2024-08-15
```