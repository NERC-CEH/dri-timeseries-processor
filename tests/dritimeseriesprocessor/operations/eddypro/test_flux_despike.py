"""Tests for MAD despiking (flux_despike) and EddyProRun._run_despiking."""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.eddypro.eddypro_run_method import EddyProRun
from dritimeseriesprocessor.operations.eddypro.flux_despike import despike_df, spike_code
from dritimeseriesprocessor.utils.enums import ProcessingLevel

# ---------------------------------------------------------------------------
# spike_code
# ---------------------------------------------------------------------------


class TestSpikeCode:
    def _make_series(self, n: int = 96) -> tuple[pl.Series, pl.Series]:
        """Return (var, rg) with no spikes — flat signal with daytime radiation."""
        var = pl.Series("H", [10.0] * n)
        rg = pl.Series("R_SW_in_Avg", [100.0] * n)
        return var, rg

    def test_returns_series_same_length(self) -> None:
        var, rg = self._make_series()
        result = spike_code(var, rg, sensitivity=5.5, window_days=2)
        assert len(result) == len(var)

    def test_no_spikes_when_signal_is_flat(self) -> None:
        var, rg = self._make_series(96)
        result = spike_code(var, rg, sensitivity=5.5, window_days=2)
        assert result.null_count() == 0

    def test_spike_is_set_to_null(self) -> None:
        """Insert an obvious spike and verify it is set to NaN."""
        n = 96
        values = [10.0] * n
        values[48] = 10000.0  # large spike
        var = pl.Series("H", values)
        rg = pl.Series("R_SW_in_Avg", [100.0] * n)
        result = spike_code(var, rg, sensitivity=5.5, window_days=2)
        assert np.isnan(result[48])

    def test_preserves_series_name(self) -> None:
        var, rg = self._make_series()
        result = spike_code(var, rg, sensitivity=5.5, window_days=2)
        assert result.name == "H"


# ---------------------------------------------------------------------------
# despike_df
# ---------------------------------------------------------------------------


def _make_eddypro_df(n: int = 48, h_values: list[float] | None = None) -> pl.DataFrame:
    times = [datetime(2026, 1, 20, 0, 0) + timedelta(minutes=30 * i) for i in range(n)]
    h = h_values if h_values is not None else [50.0] * n
    return pl.DataFrame(
        {
            "time": times,
            "H": h,
            "Tau": [0.1] * n,
            "R_SW_in_Avg": [100.0] * n,
        }
    )


def _make_history_df(n_days: int = 5) -> pl.DataFrame:
    n = n_days * 48
    times = [datetime(2026, 1, 15, 0, 0) + timedelta(minutes=30 * i) for i in range(n)]
    return pl.DataFrame(
        {
            "time": times,
            "H": [50.0] * n,
            "Tau": [0.1] * n,
            "R_SW_in_Avg": [100.0] * n,
        }
    )


class TestDespikeDf:
    def test_adds_h_despiked_and_tau_l2_columns(self) -> None:
        current = _make_eddypro_df()
        history = _make_history_df()
        result = despike_df(
            current,
            history,
            columns=["H", "Tau"],
            reference_column="R_SW_in_Avg",
            output_names={"H": "H_despiked", "Tau": "Tau_L2"},
        )
        assert "H_despiked" in result.columns
        assert "Tau_L2" in result.columns

    def test_adds_h_l2_column(self) -> None:
        current = _make_eddypro_df()
        history = _make_history_df()
        result = despike_df(current, history, columns=["H", "Tau"], reference_column="R_SW_in_Avg")
        assert "H_L2" in result.columns

    def test_returns_only_current_rows(self) -> None:
        current = _make_eddypro_df(n=48)
        history = _make_history_df(n_days=5)
        result = despike_df(current, history, columns=["H", "Tau"], reference_column="R_SW_in_Avg")
        assert len(result) == 48

    def test_h_l2_range_check_clips_out_of_range(self) -> None:
        """Values outside [-200, 600] should become null in H_L2."""
        h_values = [50.0] * 48
        h_values[10] = 700.0  # above 600 — should be nulled in H_L2
        h_values[20] = -250.0  # below -200 — should be nulled in H_L2
        current = _make_eddypro_df(h_values=h_values)
        history = _make_history_df()
        result = despike_df(current, history, columns=["H", "Tau"], reference_column="R_SW_in_Avg", iterations=0)
        assert np.isnan(result["H_L2"][10])
        assert np.isnan(result["H_L2"][20])

    def test_normal_h_values_pass_range_check(self) -> None:
        current = _make_eddypro_df()
        history = _make_history_df()
        result = despike_df(current, history, columns=["H", "Tau"], reference_column="R_SW_in_Avg")
        assert result["H_L2"].null_count() == 0


# ---------------------------------------------------------------------------
# EddyProRun._run_despiking
# ---------------------------------------------------------------------------


PROCESSED_URL = "s3://ukceh-dri-staging-processed/network=FDRI/collection=PROCESSED_30MIN/site=PLYNL"


def _make_container(
    site: str = "flux-plynl",
    access_url: str = "s3://source-bucket/network=FDRI/collection=PROCESSED_FLUX/site=PLYNL",
) -> TimeSeriesContainer:
    """Real container so dataclasses.replace works inside _run_despiking."""
    return TimeSeriesContainer(
        ts_id="flux-plynl-processed",
        network="fdri",
        source_column=None,
        source_site=None,
        source_site_identifier=site,
        time_column_name="TIMESTAMP",
        unit=None,
        resolution="PT30M",
        periodicity="PT30M",
        time_anchor="start",
        processing_level=ProcessingLevel.PROCESSED,
        access_url=access_url,
    )


def _make_site_metadata(network: str = "fdri") -> MagicMock:
    metadata = MagicMock()
    metadata.network = network
    return metadata


class TestRunDespiking:
    def test_skips_when_history_is_empty(self) -> None:
        """Tests that the original data is returned unchanged when the history is empty."""
        mock_router = MagicMock()
        mock_router.query_by_date_range.return_value = pl.DataFrame()

        current = _make_eddypro_df()
        result = EddyProRun._run_despiking(
            df=current,
            container=_make_container(),
            start_date=date(2026, 1, 20),
            data_router=mock_router,
            processed_access_url=PROCESSED_URL,
        )

        assert_frame_equal(result, current)

    def test_skips_when_history_is_none(self) -> None:
        """Tests that the original data is returned unchanged when the router returns no history."""
        mock_router = MagicMock()
        mock_router.query_by_date_range.return_value = None

        current = _make_eddypro_df()
        result = EddyProRun._run_despiking(
            df=current,
            container=_make_container(),
            start_date=date(2026, 1, 20),
            data_router=mock_router,
            processed_access_url=PROCESSED_URL,
        )

        assert_frame_equal(result, current)

    def test_skips_when_history_fails_to_load(self) -> None:
        """Tests that the original data is returned unchanged when reading the history raises an error."""
        mock_router = MagicMock()
        mock_router.query_by_date_range.side_effect = ValueError("read failed")

        current = _make_eddypro_df()
        result = EddyProRun._run_despiking(
            df=current,
            container=_make_container(),
            start_date=date(2026, 1, 20),
            data_router=mock_router,
            processed_access_url=PROCESSED_URL,
        )

        assert_frame_equal(result, current)

    def test_skips_without_reading_when_no_access_url(self, caplog: pytest.LogCaptureFixture) -> None:
        """Tests that despiking is skipped, with a warning and no read, when there is no access URL for the history."""
        mock_router = MagicMock()

        current = _make_eddypro_df()
        result = EddyProRun._run_despiking(
            df=current,
            container=_make_container(),
            start_date=date(2026, 1, 20),
            data_router=mock_router,
            processed_access_url=None,
        )

        assert_frame_equal(result, current)
        mock_router.query_by_date_range.assert_not_called()
        assert "no processed timeseries dataset to read history from" in caplog.text

    def test_happy_path_adds_despiked_columns(self) -> None:
        """Tests that despiked columns are added when history is available."""
        history = _make_history_df(n_days=5)
        mock_router = MagicMock()
        mock_router.query_by_date_range.return_value = history

        current = _make_eddypro_df()
        result = EddyProRun._run_despiking(
            df=current,
            container=_make_container(),
            start_date=date(2026, 1, 20),
            data_router=mock_router,
            processed_access_url=PROCESSED_URL,
        )

        assert "H_despiked" in result.columns
        assert "Tau_L2" in result.columns
        assert "H_L2" in result.columns

    def test_lookback_window_passed_to_router(self) -> None:
        """Tests that the history is read for the lookback days before the processing window."""
        mock_router = MagicMock()
        mock_router.query_by_date_range.return_value = pl.DataFrame()

        EddyProRun._run_despiking(
            df=_make_eddypro_df(),
            container=_make_container(),
            start_date=date(2026, 1, 20),
            data_router=mock_router,
            processed_access_url=PROCESSED_URL,
        )

        call_kwargs = mock_router.query_by_date_range.call_args.kwargs
        expected_start = datetime(2026, 1, 20) - timedelta(days=EddyProRun._DESPIKE_LOOKBACK_DAYS)
        expected_end = datetime(2026, 1, 19)
        assert call_kwargs["start_date"] == expected_start
        assert call_kwargs["end_date"] == expected_end

    def test_history_containers_read_from_given_access_url(self) -> None:
        """Tests that one history container is built per column to despike, all read from the given access URL."""
        mock_router = MagicMock()
        mock_router.query_by_date_range.return_value = pl.DataFrame()

        EddyProRun._run_despiking(
            df=_make_eddypro_df(),
            container=_make_container(),
            start_date=date(2026, 1, 20),
            data_router=mock_router,
            processed_access_url=PROCESSED_URL,
        )

        containers = mock_router.query_by_date_range.call_args.args
        assert all(container.access_url == PROCESSED_URL for container in containers)
        assert all(container.time_column_name == "time" for container in containers)
        assert {container.source_column for container in containers} == {"H", "Tau", "R_SW_in_Avg"}
