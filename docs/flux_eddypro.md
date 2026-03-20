# Flux / EddyPro

This repo has a separate `eddypro` CLI mode for running EddyPro against raw flux files.

It still uses the normal dependency graph, but runs a file-based EddyPro workflow instead of the in-memory time-series pipeline.

## What it does

The `eddypro` mode:

- selects a network and site from the CLI
- resolves local metadata fixtures for local development
- stages raw flux `.dat` files from S3
- builds EddyPro config files from templates
- runs `eddypro_rp` and `eddypro_fcc`
- uploads the outputs back to the processed bucket

## Relevant code

- CLI parsing: `src/dritimeseriesprocessor/cli/cli.py`
- App entrypoint: `src/dritimeseriesprocessor/app/run.py`
- Main processor: `src/dritimeseriesprocessor/processing/time_series_processor.py`
- Flux S3 helper: `src/dritimeseriesprocessor/io_backend/flux_io.py`
- Local metadata adapter: `src/dritimeseriesprocessor/routers/metadata/local_eddypro_metadata_source.py`
- Temporary local graph loader: `src/dritimeseriesprocessor/routers/metadata/flux_metadata_loader.py`
- EddyPro config and runner code: `src/dritimeseriesprocessor/operations/eddypro/`
- EddyPro templates: `src/dritimeseriesprocessor/__assets__/eddypro_templates/`
- Local EddyPro metadata fixtures: `src/dritimeseriesprocessor/__metadata__/eddypro/`

## Local requirements

- LocalStack running for S3
- local config pointing at LocalStack in `src/dritimeseriesprocessor/__assets__/env.cfg`
- `eddypro_rp` and `eddypro_fcc` available on `PATH`

If you run inside the project container, the binaries may already be present there. If you run on your host machine, your host still needs access to them.

## Expected S3 layout

For a site like `PLYNL` and a raw source dataset like `Flux`, the local EddyPro path expects raw files under:

- `fdri/dataset=Flux/site=PLYNL/date=YYYY-MM-DD/`

Outputs are uploaded to the processed bucket under:

- `fdri/dataset=<PROCESSED_DATASET>/site=PLYNL/date=YYYY-MM-DD/`

## Local metadata fixtures

For local development, EddyPro metadata is loaded from simplified JSON files under:

- `src/dritimeseriesprocessor/__metadata__/eddypro/network.json`
- `src/dritimeseriesprocessor/__metadata__/eddypro/sites.json`
- `src/dritimeseriesprocessor/__metadata__/eddypro/datasets.json`
- `src/dritimeseriesprocessor/__metadata__/eddypro/processing_configs.json`

These are local fixtures for development and demos until the real metadata path is wired in.

## Running it

Example:

```bash
python -m dritimeseriesprocessor eddypro \
  --network fdri \
  --sites PLYNL \
  --start-date 2024-08-14 \
  --end-date 2024-08-15
