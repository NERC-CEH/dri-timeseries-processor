"""Tests for MAD despiking (flux_despike) and EddyProRun._run_despiking."""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.derivation.derivation_methods import EddyProRun
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
            current, history,
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


def _make_container(site: str = "flux-plynl", source_bucket: str = "source-bucket") -> TimeSeriesContainer:
    """Real container so dataclasses.replace works inside _run_despiking."""
    return TimeSeriesContainer(
        ts_id="flux-plynl-processed",
        network="fdri",
        source_bucket=source_bucket,
        source_dataset="PROCESSED",
        source_column=None,
        source_site=None,
        source_site_identifier=site,
        time_column_name="time",
        resolution="PT30M",
        periodicity="PT30M",
        processing_level=ProcessingLevel.PROCESSED,
    )


def _make_site_metadata(network: str = "fdri") -> MagicMock:
    metadata = MagicMock()
    metadata.network = network
    return metadata


class TestRunDespiking:
    def test_skips_when_history_is_empty(self, caplog) -> None:
        """_run_despiking returns the original df unchanged when no history is available."""
        mock_router = MagicMock()
        mock_router.query_by_date_range.return_value = pl.DataFrame()

        current = _make_eddypro_df()
        result = EddyProRun._run_despiking(
            df=current,
            container=_make_container(),
            start_date=date(2026, 1, 20),
            resolution="PT30M",
            data_router=mock_router,
            processed_container=_make_container(),
        )

        assert_frame_equal(result, current)

    def test_skips_when_history_is_none(self) -> None:
        mock_router = MagicMock()
        mock_router.query_by_date_range.return_value = None

        current = _make_eddypro_df()
        result = EddyProRun._run_despiking(
            df=current,
            container=_make_container(),
            start_date=date(2026, 1, 20),
            resolution="PT30M",
            data_router=mock_router,
            processed_container=_make_container(),
        )

        assert_frame_equal(result, current)

    def test_happy_path_adds_despiked_columns(self) -> None:
        history = _make_history_df(n_days=5)
        mock_router = MagicMock()
        mock_router.query_by_date_range.return_value = history

        current = _make_eddypro_df()
        result = EddyProRun._run_despiking(
            df=current,
            container=_make_container(),
            start_date=date(2026, 1, 20),
            resolution="PT30M",
            data_router=mock_router,
            processed_container=_make_container(),
        )

        assert "H_despiked" in result.columns
        assert "Tau_L2" in result.columns
        assert "H_L2" in result.columns

    def test_lookback_window_passed_to_router(self) -> None:
        mock_router = MagicMock()
        mock_router.query_by_date_range.return_value = pl.DataFrame()

        EddyProRun._run_despiking(
            df=_make_eddypro_df(),
            container=_make_container(),
            start_date=date(2026, 1, 20),
            resolution="PT30M",
            data_router=mock_router,
            processed_container=_make_container(),
        )

        call_kwargs = mock_router.query_by_date_range.call_args.kwargs
        expected_start = date(2026, 1, 20) - timedelta(days=EddyProRun._DESPIKE_LOOKBACK_DAYS)
        expected_end = date(2026, 1, 19)
        assert call_kwargs["start_date"] == expected_start
        assert call_kwargs["end_date"] == expected_end

    def test_history_containers_built_from_metadata(self) -> None:
        """The per-column history containers carry the network, bucket and columns to despike."""
        mock_router = MagicMock()
        mock_router.query_by_date_range.return_value = pl.DataFrame()

        EddyProRun._run_despiking(
            df=_make_eddypro_df(),
            container=_make_container(),
            start_date=date(2026, 1, 20),
            resolution="PT30M",
            data_router=mock_router,
            processed_container=_make_container(source_bucket="ukceh-dri-staging-processed"),
        )

        containers = mock_router.query_by_date_range.call_args.args
        assert all(c.network == "fdri" for c in containers)
        assert all(c.source_bucket == "ukceh-dri-staging-processed" for c in containers)
        assert all(c.processing_level is ProcessingLevel.PROCESSED for c in containers)
        assert all(c.resolution == "PT30M" for c in containers)
        assert {c.source_column for c in containers} == {"H", "Tau", "R_SW_in_Avg"}
