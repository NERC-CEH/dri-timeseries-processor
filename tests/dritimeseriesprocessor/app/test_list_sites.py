import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from dritimeseriesprocessor.app.run import list_sites
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.utils.urls import SITE_URI


def make_sites_response(site_ids: list[str]) -> MagicMock:
    """Build a fake fetch_sites_by_network response for the given short site IDs."""
    response = MagicMock()
    response.items = [MagicMock(id=f"{SITE_URI}/{site_id}") for site_id in site_ids]
    return response


def make_site_metadata(site_id: str, start_date: datetime, end_date: datetime | None = None) -> SiteMetadata:
    return SiteMetadata(
        site_id=f"{SITE_URI}/{site_id}",
        network="cosmos",
        start_date=start_date,
        end_date=end_date,
    )


class TestListSites:
    def _setup_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENVIRONMENT", "staging")
        monkeypatch.setenv("metadata_api_url", "http://fake-api")
        monkeypatch.setenv("pushgateway_url", "http://fake-pushgateway")

    def test_writes_site_ids_to_json_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._setup_env(monkeypatch)
        monkeypatch.setattr(
            "dritimeseriesprocessor.app.run.MetadataRouter.fetch_sites_by_network",
            lambda _self, _network: make_sites_response(["cosmos-alic1", "cosmos-bunny"]),
        )
        monkeypatch.setattr(
            "dritimeseriesprocessor.app.run.map_site_metadata",
            lambda item: make_site_metadata(item.id.removeprefix(f"{SITE_URI}/"), datetime(2000, 1, 1)),
        )

        list_sites("cosmos", datetime(2024, 1, 1), datetime(2025, 1, 1))

        with open("/tmp/sites.json") as f:
            assert json.load(f) == ["cosmos-alic1", "cosmos-bunny"]

    def test_filters_out_inactive_sites(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sites whose end_date falls before window_start are excluded."""
        self._setup_env(monkeypatch)
        monkeypatch.setattr(
            "dritimeseriesprocessor.app.run.MetadataRouter.fetch_sites_by_network",
            lambda _self, _network: make_sites_response(["cosmos-alic1", "cosmos-bunny"]),
        )
        # mock that alic1 closed before the window; bunny is still active
        site_metas = {
            "cosmos-alic1": make_site_metadata("cosmos-alic1", datetime(2000, 1, 1), datetime(2023, 6, 1)),
            "cosmos-bunny": make_site_metadata("cosmos-bunny", datetime(2000, 1, 1)),
        }
        monkeypatch.setattr(
            "dritimeseriesprocessor.app.run.map_site_metadata",
            lambda item: site_metas[item.id.removeprefix(f"{SITE_URI}/")],
        )

        list_sites("cosmos", datetime(2024, 1, 1), datetime(2025, 1, 1))

        with open("/tmp/sites.json") as f:
            assert json.load(f) == ["cosmos-bunny"]

    def test_empty_network_writes_empty_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._setup_env(monkeypatch)
        monkeypatch.setattr(
            "dritimeseriesprocessor.app.run.MetadataRouter.fetch_sites_by_network",
            lambda _self, _network: make_sites_response([]),
        )

        list_sites("cosmos", datetime(2024, 1, 1), datetime(2025, 1, 1))

        with open("/tmp/sites.json") as f:
            assert json.load(f) == []
