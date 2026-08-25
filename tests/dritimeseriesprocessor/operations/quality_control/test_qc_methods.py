from datetime import datetime
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_series_equal

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.quality_control.qc_methods import (
    BatteryVoltage,
    ErrorCode,
    FluxQcFlag,
    HeatFluxPlateRemoval,
    ManualRemoval,
    Nr01Temp,
    PluvioDiagnostic,
    Range,
    Samples,
    SnowDaySignal,
    Spike,
    TdtTSoil,
)
from utils.data_creation import create_timeframe

MANUAL_FLAGS_HEADER = '"SITE_ID","VARIABLES_AFFECTED","START_DATETIME","END_DATETIME"'


def create_method_config(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    **extra_params,
) -> DataProcessingMethodConfig:
    """Create a test MethodConfig.

    Args:
        start_date: Start date for the config
        end_date: End date for the config
        **extra_params: Additional parameters to add to config.params

    Returns:
        MethodConfig for testing
    """
    params = {}
    params.update(extra_params)

    return DataProcessingMethodConfig(
        method="test",
        params=params,
        start_date=start_date,
        end_date=end_date,
    )


class TestRange:
    def test_range_simple(self) -> None:
        """Test that the range function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(lt=3, gt=5)

        result = Range().run(tf, config)

        expected = pl.Series([True, True, False, False, False, True, True])
        assert_series_equal(result, expected)

    def test_range_with_date_filter(self) -> None:
        """Test that the range function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            lt=3,
            gt=5,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = Range().run(tf, config)

        expected = pl.Series([False, False, False, False, False, False, False])
        assert_series_equal(result, expected)


class TestBatteryVoltage:
    def test_battv_simple(self) -> None:
        """Test that the BatteryVoltage function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(lt=4)

        result = BatteryVoltage().run(tf, config)

        expected = pl.Series([True, True, True, False, False, False, False])
        assert_series_equal(result, expected)

    def test_battv_with_date_filter(self) -> None:
        """Test that the BatteryVoltage function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            lt=4,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = BatteryVoltage().run(tf, config)

        expected = pl.Series([False, False, True, False, False, False, False])
        assert_series_equal(result, expected)


class TestSamples:
    def test_samples_simple(self) -> None:
        """Test that the samples function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(lt=4)

        result = Samples().run(tf, config)

        expected = pl.Series([True, True, True, False, False, False, False])
        assert_series_equal(result, expected)

    def test_samples_with_date_filter(self) -> None:
        """Test that the samples function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            lt=4,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = Samples().run(tf, config)

        expected = pl.Series([False, False, True, False, False, False, False])
        assert_series_equal(result, expected)


class TestErrorCode:
    def test_error_code_simple(self) -> None:
        """Test that the error code function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(value=[5.0, 6.0, 7.0])

        result = ErrorCode().run(tf, config)

        expected = pl.Series([False, False, False, False, True, True, True])
        assert_series_equal(result, expected)

    def test_error_code_with_date_filter(self) -> None:
        """Test that the error code function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            value=[5.0, 6.0, 7.0],
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = ErrorCode().run(tf, config)

        expected = pl.Series([False, False, False, False, True, False, False])
        assert_series_equal(result, expected)


class TestSpike:
    def test_spike_simple(self) -> None:
        """Test that the spike function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 30.0, 4.0, 5.0, 60.0, 7.0])
        config = create_method_config(gt=5.0)

        result = Spike().run(tf, config)

        expected = pl.Series([None, False, True, False, False, True, None])
        assert_series_equal(result, expected)

    def test_spike_with_date_filter(self) -> None:
        """Test that the spike function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 30.0, 4.0, 5.0, 60.0, 7.0])
        config = create_method_config(
            gt=5.0,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = Spike().run(tf, config)

        expected = pl.Series([False, False, True, False, False, False, False])
        assert_series_equal(result, expected)


class TestNr01Temp:
    def test_nr01_simple(self) -> None:
        """Test that the nr01 function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(lt=3, gt=5)

        result = Nr01Temp().run(tf, config)

        expected = pl.Series([True, True, False, False, False, True, True])
        assert_series_equal(result, expected)

    def test_nr01_with_date_filter(self) -> None:
        """Test that the nr01 function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            lt=3,
            gt=5,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = Nr01Temp().run(tf, config)

        expected = pl.Series([False, False, False, False, False, False, False])
        assert_series_equal(result, expected)


class TestHeatFluxPlateRemoval:
    def test_hfp_simple(self) -> None:
        """Test that the hfp removal function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(time_ge="01:00:00", time_le="03:00:00")

        result = HeatFluxPlateRemoval().run(tf, config)

        expected = pl.Series([False, True, True, True, False, False, False])
        assert_series_equal(result, expected)

    def test_hfp_with_date_filter(self) -> None:
        """Test that the hfp removal function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            time_ge="01:00:00",
            time_le="03:00:00",
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = HeatFluxPlateRemoval().run(tf, config)

        expected = pl.Series([False, False, True, True, False, False, False])
        assert_series_equal(result, expected)


class TestPluvioDiagnostic:
    def test_pluvio_diagnostic_simple(self) -> None:
        """Test that the pluvio_diagnostic function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(gt=4)

        result = PluvioDiagnostic().run(tf, config)

        expected = pl.Series([False, False, False, False, True, True, True])
        assert_series_equal(result, expected)

    def test_pluvio_diagnostic_with_date_filter(self) -> None:
        """Test that the pluvio_diagnostic function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            gt=4,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = PluvioDiagnostic().run(tf, config)

        expected = pl.Series([False, False, False, False, True, False, False])
        assert_series_equal(result, expected)


class TestSnowDaySignal:
    def test_snowday_simple(self) -> None:
        """Test that the snowday function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(lt=4)

        result = SnowDaySignal().run(tf, config)

        expected = pl.Series([True, True, True, False, False, False, False])
        assert_series_equal(result, expected)

    def test_snowday_with_date_filter(self) -> None:
        """Test that the snowday function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            lt=4,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = SnowDaySignal().run(tf, config)

        expected = pl.Series([False, False, True, False, False, False, False])
        assert_series_equal(result, expected)


class TestTdtTSoil:
    def test_tdt_soil_simple(self) -> None:
        """Test that the tdt_soil function works across the full DataFrame."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(lt=4)

        result = TdtTSoil().run(tf, config)

        expected = pl.Series([True, True, True, False, False, False, False])
        assert_series_equal(result, expected)

    def test_tdt_soil_with_date_filter(self) -> None:
        """Test that the tdt_soil function works with a date filter."""
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(
            lt=4,
            start_date=datetime(2025, 1, 1, 2),
            end_date=datetime(2025, 1, 1, 4, 59),
        )

        result = TdtTSoil().run(tf, config)

        expected = pl.Series([False, False, True, False, False, False, False])
        assert_series_equal(result, expected)


class TestFluxQcFlag:
    def test_flags_poor_quality_rows(self) -> None:
        """Flag value 2 (poor quality) is rejected; 0 and 1 are not."""
        tf = create_timeframe([0.0, 1.0, 2.0, 0.0, 2.0])
        config = create_method_config()

        result = FluxQcFlag().run(tf, config)

        expected = pl.Series([False, False, True, False, True])
        assert_series_equal(result, expected, check_names=False)

    def test_no_poor_quality_rows(self) -> None:
        """No flag value 2 → all False."""
        tf = create_timeframe([0.0, 1.0, 0.0, 1.0])
        config = create_method_config()

        result = FluxQcFlag().run(tf, config)

        expected = pl.Series([False, False, False, False])
        assert_series_equal(result, expected, check_names=False)


class TestManualRemoval:
    def use_periods(self, monkeypatch: pytest.MonkeyPatch, *periods: tuple) -> None:
        """Use the given flagged periods rather than the file shipped with the package.

        Args:
            monkeypatch: Fixture used to replace the lookup.
            periods: (start, end) pairs to return for any site and variable.
        """
        monkeypatch.setattr(ManualRemoval, "flag_periods", lambda self, network, site_id, column_name: list(periods))

    def use_loaded_flags(self, monkeypatch: pytest.MonkeyPatch, loaded_flags: dict) -> None:
        """Use the given loaded flags rather than reading the file shipped with the package.

        Args:
            monkeypatch: Fixture used to replace the file read.
            loaded_flags: Flagged periods keyed by (site ID, variable name).
        """
        monkeypatch.setattr(ManualRemoval, "load_manual_flags", staticmethod(lambda file_path: loaded_flags))

    def write_manual_flags(self, tmp_path: Path, *rows: str) -> Path:
        """Write a manual flagging file made up of the given rows.

        Args:
            tmp_path: Directory to write the file into.
            rows: Rows to write below the header.

        Returns:
            Path of the file that was written.
        """
        file_path = tmp_path / "manual_flags.csv"
        file_path.write_text("\n".join([MANUAL_FLAGS_HEADER, *rows]) + "\n")
        return file_path

    def test_manual_removal_simple(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that values inside a flagged period are flagged."""
        self.use_periods(monkeypatch, (datetime(2025, 1, 1, 2), datetime(2025, 1, 1, 4)))
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(site_id="ALIC1", network="cosmos")

        result = ManualRemoval().run(tf, config)

        expected = pl.Series([False, False, True, True, True, False, False])
        assert_series_equal(result, expected, check_names=False)

    def test_manual_removal_nothing_flagged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that nothing is flagged when the site and variable have no flagged periods."""
        self.use_periods(monkeypatch)
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(site_id="ALIC1", network="cosmos")

        result = ManualRemoval().run(tf, config)

        expected = pl.Series([False, False, False, False, False, False, False])
        assert_series_equal(result, expected, check_names=False)

    def test_manual_removal_open_ended_period(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a period with no end date runs to the end of the data."""
        self.use_periods(monkeypatch, (datetime(2025, 1, 1, 4), None))
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(site_id="ALIC1", network="cosmos")

        result = ManualRemoval().run(tf, config)

        expected = pl.Series([False, False, False, False, True, True, True])
        assert_series_equal(result, expected, check_names=False)

    def test_manual_removal_single_time_period(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a period with the same start and end date flags a single value."""
        self.use_periods(monkeypatch, (datetime(2025, 1, 1, 3), datetime(2025, 1, 1, 3)))
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(site_id="ALIC1", network="cosmos")

        result = ManualRemoval().run(tf, config)

        expected = pl.Series([False, False, False, True, False, False, False])
        assert_series_equal(result, expected, check_names=False)

    def test_manual_removal_multiple_periods(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that values in any of several flagged periods are flagged."""
        self.use_periods(
            monkeypatch,
            (datetime(2025, 1, 1, 1), datetime(2025, 1, 1, 2)),
            (datetime(2025, 1, 1, 5), datetime(2025, 1, 1, 6)),
        )
        tf = create_timeframe([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        config = create_method_config(site_id="ALIC1", network="cosmos")

        result = ManualRemoval().run(tf, config)

        expected = pl.Series([False, True, True, False, False, True, True])
        assert_series_equal(result, expected, check_names=False)

    def test_splits_variables_on_semicolon(self, tmp_path: Path) -> None:
        """Test that a ";" separated variable list becomes one entry per variable."""
        file_path = self.write_manual_flags(tmp_path, '"ALIC1","TA;RH",2015-03-06 00:00:00,2015-03-06 12:00:00')

        result = ManualRemoval.load_manual_flags(file_path)

        period = (datetime(2015, 3, 6), datetime(2015, 3, 6, 12))
        assert result == {("ALIC1", "TA"): [period], ("ALIC1", "RH"): [period]}

    def test_empty_end_datetime_is_open_ended(self, tmp_path: Path) -> None:
        """Test that a row with no end date gives a period with no end."""
        file_path = self.write_manual_flags(tmp_path, '"ALIC1","TA",2015-03-06 00:00:00,')

        result = ManualRemoval.load_manual_flags(file_path)

        assert result == {("ALIC1", "TA"): [(datetime(2015, 3, 6), None)]}

    def test_empty_variable_is_ignored(self, tmp_path: Path) -> None:
        """Test that a trailing ";" in the variable list does not create an empty entry."""
        file_path = self.write_manual_flags(tmp_path, '"ALIC1","TA;",2015-03-06 00:00:00,2015-03-06 12:00:00')

        result = ManualRemoval.load_manual_flags(file_path)

        assert list(result) == [("ALIC1", "TA")]

    def test_periods_for_same_variable_are_collected(self, tmp_path: Path) -> None:
        """Test that several rows for one site and variable give several periods."""
        file_path = self.write_manual_flags(
            tmp_path,
            '"ALIC1","TA",2015-03-06 00:00:00,2015-03-06 12:00:00',
            '"ALIC1","TA",2016-01-01 00:00:00,2016-01-02 00:00:00',
        )

        result = ManualRemoval.load_manual_flags(file_path)

        assert result == {
            ("ALIC1", "TA"): [
                (datetime(2015, 3, 6), datetime(2015, 3, 6, 12)),
                (datetime(2016, 1, 1), datetime(2016, 1, 2)),
            ]
        }

    def test_flag_periods_includes_all_variables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that periods recorded against "ALL" are returned alongside a variable's own periods."""
        self.use_loaded_flags(
            monkeypatch,
            {
                ("ALIC1", "TA"): [(datetime(2015, 3, 6), datetime(2015, 3, 6, 12))],
                ("ALIC1", "ALL"): [(datetime(2021, 4, 13), None)],
            },
        )

        assert ManualRemoval().flag_periods("cosmos", "ALIC1", "TA") == [
            (datetime(2015, 3, 6), datetime(2015, 3, 6, 12)),
            (datetime(2021, 4, 13), None),
        ]
        assert ManualRemoval().flag_periods("cosmos", "ALIC1", "SWIN") == [(datetime(2021, 4, 13), None)]

    def test_flag_periods_unknown_site_returns_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a site or variable that is not in the file returns no periods."""
        self.use_loaded_flags(monkeypatch, {("BUNNY", "TA"): [(datetime(2016, 1, 1), datetime(2016, 1, 2))]})

        assert ManualRemoval().flag_periods("cosmos", "NOSUCH", "TA") == []
        assert ManualRemoval().flag_periods("cosmos", "BUNNY", "SWIN") == []
