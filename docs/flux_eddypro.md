# Flux / EddyPro

This repo contains an Flux processing path that runs **LI-COR EddyPro** locally and shuttles inputs/outputs via S3 (LocalStack for dev).

This is not part of the main time-series “selection model” and is intentionally kept separate while we iterate.

## What This Does

The `flux` CLI mode:

- Downloads raw flux files for a site + day from S3
- Downloads site ancillary inputs (dynamic metadata + biomet) from S3
- Renders EddyPro config files from templates + a local per-site JSON config
- Runs `eddypro_rp` then `eddypro_fcc`
- Uploads generated configs, logs, and outputs back to S3

Relevant code:

- CLI parsing: `src/dritimeseriesprocessor/cli/cli.py`
- Run entrypoint: `src/dritimeseriesprocessor/app/run.py`
- EddyPro runner + templates: `src/dritimeseriesprocessor/eddypro/runner.py`, `src/dritimeseriesprocessor/eddypro/templates/`
- Local run config loader: `src/dritimeseriesprocessor/eddypro/run_config.py`

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

The runner uses these prefixes (for `network=flux`, `site=PLYNL`, `source_dataset=raw_flux`):

- Raw inputs:
  - `flux/dataset=raw_flux/site=PLYNL/date=YYYY-MM-DD/`
- Ancillary inputs:
  - `flux/ancillary/dynamic_metadata/site=PLYNL/`
  - `flux/ancillary/biomet/site=PLYNL/`
- Outputs (to the processed bucket):
  - `flux/dataset=eddypro_flux/site=PLYNL/date=YYYY-MM-DD/`
    - `generated/` (rendered `.eddypro` + `.metadata`)
    - `logs/` (`eddypro_rp.log`, `eddypro_fcc.log`)
    - `output/PLYNL/` (EddyPro outputs)

## Local Fixtures

LocalStack initialisation uploads everything under `flux-data/` into the level-0 bucket (except `local_config/`), via `bin/localstack-setup.sh`.

Current example fixtures are under:

- `flux-data/flux/dataset=raw_flux/site=PLYNL/date=2024-08-14/`
- `flux-data/flux/ancillary/dynamic_metadata/site=PLYNL/`
- `flux-data/flux/local_config/site=PLYNL/site_config.json` (local-only, not uploaded)


## Running It

Example (single site):

```bash
python -m dritimeseriesprocessor flux \
  --network flux \
  --sites PLYNL \
  --start-date 2024-08-14 \
  --end-date 2024-08-15
```

## Adding Another Site

1. Add local config JSON:
   - `flux-data/flux/local_config/site=<SITE>/site_config.json`
2. Add fixtures for LocalStack upload:
   - `flux-data/flux/dataset=<SOURCE_DATASET>/site=<SITE>/date=YYYY-MM-DD/...`
   - `flux-data/flux/ancillary/dynamic_metadata/site=<SITE>/...`
   - `flux-data/flux/ancillary/biomet/site=<SITE>/...`
3. Restart LocalStack to reload fixtures:
   - `docker compose down && docker compose up -d`

## Status / Limitations

- This is for demonstrating the integration pattern (S3 fixtures → template rendering → EddyPro run → S3 artifacts).
- Per-site configuration is currently loaded from `flux-data/.../local_config/...`.
- The runner creates a scratch workdir under `/tmp/driflux/eddypro/` and cleans it up at the end of the run.
