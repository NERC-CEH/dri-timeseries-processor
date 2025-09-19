from datetime import datetime

import polars as pl
import pytest
from time_stream import TimeSeries

from dritimeseriesprocessor.flagging.flagger import (
    add_initial_core_flags,
    core_flag_column_name,
    corrs_flag_column_name,
    infill_flag_column_name,
    initialise_core_flag_system,
    qc_flag_column_name,
    update_corrections_core_flags,
    update_infill_core_flags,
    update_quality_control_core_flags,
)


@pytest.fixture
def sample_timeseries() -> TimeSeries:
    data = {
        "timestamp": [
            datetime(2023, 1, 1, 0, 0),
            datetime(2023, 1, 1, 1, 0),
            datetime(2023, 1, 1, 2, 0),
            datetime(2023, 1, 1, 3, 0),
            datetime(2023, 1, 1, 4, 0),
        ],
        "value": [10, None, 30, None, 50],
    }
    sample_timeseries = TimeSeries(
        pl.DataFrame(data),
        time_name="timestamp",
    )
    sample_timeseries.add_flag_system("corrs_flags", {"ADD": 1})
    sample_timeseries.init_flag_column("corrs_flags", "value_CORRS_FLAG", [1, 0, 0, 0, 1])
    sample_timeseries.add_flag_system("qc_flags", {"RANGE": 1})
    sample_timeseries.init_flag_column("qc_flags", "value_QC_FLAG", [0, 1, 0, 1, 0])
    sample_timeseries.add_flag_system("infill_flags", {"INTERP": 1})
    sample_timeseries.init_flag_column("infill_flags", "value_INFILL_FLAG", [0, 0, 1, 0, 0])

    return sample_timeseries


class TestCoreFlagColumnName:
    def test_core_flag_column_name(self) -> None:
        """Test the generation of core flag column names."""
        assert core_flag_column_name("value") == "value_CORE_FLAG"
        assert core_flag_column_name("temperature") == "temperature_CORE_FLAG"


class TestCorrsFlagColumnName:
    """Unit tests for the corrs_flag_column_name function."""

    def test_standard_column_name(self) -> None:
        """
        Test that the function correctly appends '_CORRS_FLAG' to a standard column name.
        """
        assert corrs_flag_column_name("data") == "data_CORRS_FLAG"


class TestQCFlagColumnName:
    """Unit tests for the qc_flag_column_name function."""

    def test_standard_column_name(self) -> None:
        """
        Test that the function correctly appends '_QC_FLAG' to a standard column name.
        """
        assert qc_flag_column_name("data") == "data_QC_FLAG"


class TestInfillFlagColumnName:
    """Unit tests for the infill_flag_column_name function."""

    def test_standard_column_name(self) -> None:
        """
        Test that the function correctly appends '_INFILL_FLAG' to a standard column name.
        """
        assert infill_flag_column_name("data") == "data_INFILL_FLAG"


class TestInitialiseCoreFlagSystem:
    def test_initialise_core_flag_system(self, sample_timeseries: TimeSeries) -> None:
        """Test the initialisation of the core flag system."""
        ts = initialise_core_flag_system(sample_timeseries)
        assert "core_flags" in ts.flag_systems


class TestAddInitialCoreFlags:
    def test_add_initial_core_flags(self, sample_timeseries: TimeSeries) -> None:
        """Test the initial core flags of 'unchecked' (32) and 'missing' (4) are added correctly."""
        ts = add_initial_core_flags(sample_timeseries)

        flag_col = core_flag_column_name("value")

        assert flag_col in ts.flag_columns
        assert list(ts.df[flag_col]) == [32, 36, 32, 36, 32]


class TestUpdateCorrectionsCoreFlags:
    def test_update_corrections_core_flags(self, sample_timeseries: TimeSeries) -> None:
        """Test the the core flag column is updated with 'corrected' core flag (1)."""
        ts = add_initial_core_flags(sample_timeseries)
        ts = update_corrections_core_flags(sample_timeseries)
        flag_col = core_flag_column_name("value")
        assert list(ts.df[flag_col]) == [33, 36, 32, 36, 33]

    def test_no_core_flag_column(self, sample_timeseries: TimeSeries) -> None:
        """Test that an error is raised if the core flag column is not found."""
        with pytest.raises(ValueError):
            update_corrections_core_flags(sample_timeseries)


class TestUpdateQualityControlCoreFlags:
    def test_update_quality_control_core_flags(self, sample_timeseries: TimeSeries) -> None:
        """Test the core flag column is updated with the 'removed' core flag (8),
        and the 'unchecked' core flag (32) is removed."""
        # Init core flags so the unchecked flag is present.
        ts = add_initial_core_flags(sample_timeseries)
        ts = update_quality_control_core_flags(ts)
        flag_col = core_flag_column_name("value")
        # Should be left with missing (4) plus removed (8) flags.
        assert list(ts.df[flag_col]) == [0, 12, 0, 12, 0]

    def test_unchecked_not_removed(self, sample_timeseries: TimeSeries) -> None:
        """Test that the 'unchecked' flag is not removed when the QC flag is missing."""
        # Init core flags so the unchecked flag is present.
        ts = add_initial_core_flags(sample_timeseries)
        ts.df = ts.df.with_columns(pl.Series("value_QC_FLAG", [0, None, 0, None, 0]))
        ts = update_quality_control_core_flags(ts)
        flag_col = core_flag_column_name("value")
        # Should be left with missing (4) plus unchecked (32) flags.
        assert list(ts.df[flag_col]) == [0, 36, 0, 36, 0]

    def test_no_core_flag_column(self, sample_timeseries: TimeSeries) -> None:
        """Test that an error is raised if the core flag column is not found."""
        with pytest.raises(ValueError):
            update_quality_control_core_flags(sample_timeseries)


class TestUpdateInfillCoreFlags:
    def test_update_infill_core_flags(self, sample_timeseries: TimeSeries) -> None:
        """Test the the core flag column is updated with the 'interpolated' core flag (2)."""
        ts = add_initial_core_flags(sample_timeseries)
        ts = update_infill_core_flags(sample_timeseries)
        flag_col = core_flag_column_name("value")
        assert list(ts.df[flag_col]) == [32, 36, 34, 36, 32]

    def test_no_core_flag_column(self, sample_timeseries: TimeSeries) -> None:
        """Test that an error is raised if the core flag column is not found."""
        with pytest.raises(ValueError):
            update_infill_core_flags(sample_timeseries)
