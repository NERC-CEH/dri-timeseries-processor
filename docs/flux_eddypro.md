# Flux / EddyPro

This repo contains an Flux processing path that runs **LI-COR EddyPro** locally and shuttles inputs/outputs via S3 (LocalStack for dev).

This is a separate CLI mode that uses the same dependency-graph model, but runs a file-based workflow via the EddyPro
binary instead of the in-memory time-series operation pipeline.

## What This Does

The `eddypro` CLI mode:

- Downloads raw flux files for a site + day from S3
- Downloads site ancillary inputs (dynamic metadata + biomet) from S3
- Builds run-specific EddyPro config files from templates + local metadata fixtures
- Runs `eddypro_rp` then `eddypro_fcc`
- Uploads EddyPro outputs back to S3 (processed bucket)

Relevant code:

- CLI parsing: `src/dritimeseriesprocessor/cli/cli.py`
- Run entrypoint: `src/dritimeseriesprocessor/app/run.py`
- EddyPro processor: `src/dritimeseriesprocessor/processing/eddypro_processor.py`
- S3 router: `src/dritimeseriesprocessor/routers/data/flux_data_router.py`
- Local metadata loader: `src/dritimeseriesprocessor/routers/metadata/flux_metadata_loader.py`
- EddyPro pipeline (config + runner): `src/dritimeseriesprocessor/operations/eddypro/`
- Templates: `src/dritimeseriesprocessor/__assets__/eddypro_templates/`
- Local metadata fixtures: `src/dritimeseriesprocessor/__metadata__/eddypro/`

## Requirements (Local Dev)

- LocalStack running (S3 only): `docker compose up -d`
- Local config set to LocalStack: `src/dritimeseriesprocessor/__assets__/env.cfg` (`endpoint_url=http://localhost:4566`)
- EddyPro binaries available on `PATH`: `eddypro_rp` and `eddypro_fcc`
  - The repo `Dockerfile` copies these into `/opt/eddypro/bin` for the container image, but your host machine still needs them if you run `python -m ...` locally.

## Installing EddyPro Engine (Linux)

If you want `eddypro_rp` / `eddypro_fcc` on your **host Linux** (outside Docker), you can build them from source.


1. Install build dependencies:

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  build-essential ca-certificates gfortran git make p7zip-full
```

2. Clone and build (example: EddyPro Engine `v7.0.9`):

```bash
git clone --depth 1 --branch "v7.0.9" "https://github.com/LI-COR-Environmental/eddypro-engine.git" engine
cd engine/prj
make rp
make fcc
```

3. Put binaries on your `PATH`:

```bash
mkdir -p "$HOME/.local/bin"
cp engine/bin/linux/eddypro_rp engine/bin/linux/eddypro_fcc "$HOME/.local/bin/"
chmod +x "$HOME/.local/bin/eddypro_rp" "$HOME/.local/bin/eddypro_fcc"
export PATH="$HOME/.local/bin:$PATH"

```

4. Verify:

```bash
command -v eddypro_rp
command -v eddypro_fcc
```

## S3 Layout Expected

The runner uses these prefixes (for `network=fdri`, `site=PLYNL`, `source_dataset=Flux`):

- Raw inputs:
  - `fdri/dataset=Flux/site=PLYNL/date=YYYY-MM-DD/`
- Ancillary inputs:
  - `fdri/ancillary/dynamic_metadata/site=PLYNL/`
  - `fdri/ancillary/biomet/site=PLYNL/`
- Outputs (to the processed bucket):
  - `fdri/dataset=<PROCESSED_DATASET>/site=PLYNL/date=YYYY-MM-DD/` (EddyPro output files)

## Local Fixtures

LocalStack initialisation uploads everything under `flux-data/` into the level-0 bucket (except `local_config/`), via `bin/localstack-setup.sh`.

Current example fixtures are under:

- `flux-data/fdri/dataset=Flux/site=PLYNL/date=2024-08-14/`
- `flux-data/fdri/ancillary/dynamic_metadata/site=PLYNL/`


## Running It

Example (single site):

```bash
python -m dritimeseriesprocessor eddypro \
  --network fdri \
  --sites PLYNL \
  --start-date 2024-08-14 \
  --end-date 2024-08-15
```

## Adding Another Site

1. Add/update local metadata fixtures:
   - `src/dritimeseriesprocessor/__metadata__/eddypro/sites.json`
   - `src/dritimeseriesprocessor/__metadata__/eddypro/datasets.json`
   - `src/dritimeseriesprocessor/__metadata__/eddypro/eddypro_configs.json`
2. Add fixtures for LocalStack upload (raw + ancillary):
   - `flux-data/fdri/dataset=<SOURCE_DATASET>/site=<SITE>/date=YYYY-MM-DD/...`
   - `flux-data/fdri/ancillary/dynamic_metadata/site=<SITE>/...`
   - `flux-data/fdri/ancillary/biomet/site=<SITE>/...`
3. Restart LocalStack to reload fixtures:
   - `docker compose down && docker compose up -d`

## Status / Limitations

- This is for demonstrating the integration pattern (S3 fixtures → template rendering → EddyPro run → S3 artifacts).
- Per-site configuration and datasets are currently loaded from `src/dritimeseriesprocessor/__metadata__/eddypro/`.
- Runs use a temporary working directory per site and clean it up at the end.
