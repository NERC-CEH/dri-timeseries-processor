"""Load EddyPro run configuration from local JSON fixtures.

For now this is local and reads fixtures from the repo. Later, this will likely
be resolved from the metadata API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dritimeseriesprocessor.configuration.app_config import AppConfig
from dritimeseriesprocessor.utils.enums import Environment

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def load_eddypro_run_config(site: str, network: str, cfg: AppConfig) -> dict[str, Any]:
    """Load a site-level EddyPro run config from local JSON."""

    path = PROJECT_ROOT / "flux-data" / network / "local_config" / f"site={site}" / "site_config.json"
    if not path.exists():
        raise SystemExit(f"Missing EddyPro run config JSON: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    return parse_eddypro_run_config(payload, network=network, source=str(path))


def parse_eddypro_run_config(payload: dict[str, Any], network: str, source: str) -> dict[str, Any]:
    """Parse JSON payload into a validated, normalised dict."""
    payload_network = payload.get("network")
    if payload_network and payload_network != network:
        raise SystemExit(f"Network mismatch in {source}: expected '{network}', found '{payload_network}'")

    project_payload = payload.get("project")
    site_payload = payload.get("site")
    storage_payload = payload.get("storage")

    if not isinstance(project_payload, dict):
        raise SystemExit(f"Missing/invalid 'project' object in {source}")
    if not isinstance(site_payload, dict):
        raise SystemExit(f"Missing/invalid 'site' object in {source}")
    if not isinstance(storage_payload, dict):
        raise SystemExit(f"Missing/invalid 'storage' object in {source}")

    try:
        cfg_out: dict[str, Any] = {
            "project": {
                "title": str(project_payload["title"]),
                "id": str(project_payload["id"]),
                "file_prototype": str(project_payload["file_prototype"]),
            },
            "site": {
                "name": str(site_payload["name"]),
                "id": str(site_payload["id"]),
                "latitude": float(site_payload["latitude"]),
                "longitude": float(site_payload["longitude"]),
                "altitude": float(site_payload["altitude"]),
            },
            "storage": {
                "source_bucket": str(storage_payload["source_bucket"]),
                "source_dataset": str(storage_payload["source_dataset"]),
                "destination_bucket": str(storage_payload["destination_bucket"]),
                "destination_dataset": str(storage_payload["destination_dataset"]),
            },
        }
    except KeyError as err:
        raise SystemExit(f"Missing required field in {source}: {err}") from err
    except (TypeError, ValueError) as err:
        raise SystemExit(f"Invalid field value in {source}: {err}") from err

    return cfg_out
