from datetime import datetime
from unittest.mock import MagicMock

import pytest

from dritimeseriesprocessor.app.run import create_run_mode, run_from_config
from dritimeseriesprocessor.app.run_modes import HistoricRun, ListSitesRun, StandardRun
from dritimeseriesprocessor.cli.selection import (
    DimensionSelection,
    HistoricRunConfig,
    HistoricSelection,
    ListSitesRunConfig,
    ListSitesSelection,
    Selection,
    StandardRunConfig,
)

CONFIG = MagicMock(metadata_api_url="http://fake-api")
START = datetime(2024, 1, 1)
END = datetime(2024, 1, 31)


class TestCreateRunMode:
    def test_standard_config_creates_a_standard_run(self) -> None:
        """Tests that a standard run config creates a StandardRun with its selection, dates and the app config."""
        selection: list[Selection] = [DimensionSelection(network="cosmos")]

        run_mode = create_run_mode(StandardRunConfig(selection, START, END), CONFIG)

        assert isinstance(run_mode, StandardRun)
        assert (run_mode.cfg, run_mode.selection, run_mode.start_date, run_mode.end_date) == (
            CONFIG,
            selection,
            START,
            END,
        )

    def test_historic_config_creates_a_historic_run(self) -> None:
        """Tests that a historic run config creates a HistoricRun with its selection and the app config."""
        selection = HistoricSelection(network="cosmos")

        run_mode = create_run_mode(HistoricRunConfig(selection), CONFIG)

        assert isinstance(run_mode, HistoricRun)
        assert (run_mode.cfg, run_mode.selection) == (CONFIG, selection)

    def test_list_sites_config_creates_a_list_sites_run(self) -> None:
        """Tests that a list-sites run config creates a ListSitesRun with its selection, dates and the app config."""
        selection = ListSitesSelection(network="cosmos")

        run_mode = create_run_mode(ListSitesRunConfig(selection, START, END), CONFIG)

        assert isinstance(run_mode, ListSitesRun)
        assert (run_mode.cfg, run_mode.selection, run_mode.start_date, run_mode.end_date) == (
            CONFIG,
            selection,
            START,
            END,
        )

    def test_list_sites_config_with_no_dates_creates_a_list_sites_run_with_no_dates(self) -> None:
        """Tests that a list-sites run config with no dates creates a ListSitesRun with no dates."""
        run_mode = create_run_mode(ListSitesRunConfig(ListSitesSelection(network="cosmos"), None, None), CONFIG)

        assert isinstance(run_mode, ListSitesRun)
        assert (run_mode.start_date, run_mode.end_date) == (None, None)


class TestRunFromConfig:
    def test_runs_the_run_mode_for_the_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tests that the run mode is created from the config and the loaded app config, and then run."""
        app_config = MagicMock()
        create_mode = MagicMock()
        monkeypatch.setattr("dritimeseriesprocessor.app.run.app_config", lambda: app_config)
        monkeypatch.setattr("dritimeseriesprocessor.app.run.create_run_mode", create_mode)
        run_config = HistoricRunConfig(HistoricSelection(network="cosmos"))

        run_from_config(run_config)

        create_mode.assert_called_once_with(run_config, app_config)
        create_mode.return_value.run.assert_called_once_with()
