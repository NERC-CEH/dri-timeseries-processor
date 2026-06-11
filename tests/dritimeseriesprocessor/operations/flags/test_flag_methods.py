from datetime import datetime

import polars as pl
import pytest
import time_stream as ts
from tests.utils.data_creation import make_time_series_container

from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.flags.flag_methods import (
    add_initial_core_flags,
    core_flag_column_name,
    initialise_flag_systems,
    update_corrections_core_flags,
    update_infill_core_flags,
    update_quality_control_core_flags,
)

# Core flag values, matching the flag systems supplied by the metadata service.
CORE_FLAGS = {
    "corrected": 1,
    "estimated": 2,
    "missing": 4,
    "removed": 8,
    "suspicious": 16,
    "unchecked": 32,
    "unsuccessful_correction": 64,
}

# Flag systems and their values for every flag column used in these tests.
FLAG_SYSTEMS = {
    "core_flags": CORE_FLAGS,
    "corrs_flags": {"ADD": 1},
    "qc_flags": {"RANGE": 1},
    "infill_flags": {"INTERP": 1},
}

# Maps each flag column to the flag system that governs it, as the metadata would define for a dataset.
FLAG_COLUMN_SCHEMES = {
    "value_CORE_FLAG": "core_flags",
    "value_CORRS_FLAG": "corrs_flags",
    "value_QC_FLAG": "qc_flags",
    "value_INFILL_FLAG": "infill_flags",
}


def sample_dataframe() -> pl.DataFrame:
    """Build the DataFrame shared by the flag method tests."""
    return pl.DataFrame(
        {
            "timestamp": [
                datetime(2023, 1, 1, 0, 0),
                datetime(2023, 1, 1, 1, 0),
                datetime(2023, 1, 1, 2, 0),
                datetime(2023, 1, 1, 3, 0),
                datetime(2023, 1, 1, 4, 0),
            ],
            "value": [10, None, 30, None, 50],
        }
    )


@pytest.fixture
def sample_container() -> TimeSeriesContainer:
    """A container whose TimeFrame has the corrs, QC, infill and core flag columns set up."""
    tf = ts.TimeFrame(sample_dataframe(), time_name="timestamp")
    tf.register_flag_system("corrs_flags", {"ADD": 1})
    tf.init_flag_column("corrs_flags", "value_CORRS_FLAG", [1, 0, 0, 0, 1])
    tf.register_flag_system("qc_flags", {"RANGE": 1})
    tf.init_flag_column("qc_flags", "value_QC_FLAG", [0, 1, 0, 1, 0])
    tf.register_flag_system("infill_flags", {"INTERP": 1})
    tf.init_flag_column("infill_flags", "value_INFILL_FLAG", [0, 0, 1, 0, 0])

    container = make_time_series_container("test")
    container.data = tf
    container.flag_column_schemes = dict(FLAG_COLUMN_SCHEMES)

    # Set up the core flag system and column, as the processor does before applying core flags.
    initialise_flag_systems(container, FLAG_SYSTEMS)

    return container


@pytest.fixture
def timeframe_without_core_flag() -> ts.TimeFrame:
    """A TimeFrame with a data column but no core flag column set up."""
    return ts.TimeFrame(sample_dataframe(), time_name="timestamp")


class TestAddInitialCoreFlags:
    def test_add_initial_core_flags(self, sample_container: TimeSeriesContainer) -> None:
        """Test the initial core flags of 'unchecked' (32) and 'missing' (4) are added correctly."""
        container = add_initial_core_flags(sample_container)
        tf = container.data
        assert tf is not None

        flag_col = core_flag_column_name("value")
        assert flag_col in tf.flag_columns
        assert list(tf.df[flag_col]) == [32, 36, 32, 36, 32]


class TestUpdateCorrectionsCoreFlags:
    def test_update_corrections_core_flags(self, sample_container: TimeSeriesContainer) -> None:
        """Test that the core flag column is updated with 'corrected' core flag (1)."""
        tf = add_initial_core_flags(sample_container).data
        assert tf is not None
        tf = update_corrections_core_flags(tf)
        flag_col = core_flag_column_name("value")
        assert list(tf.df[flag_col]) == [33, 36, 32, 36, 33]

    def test_no_core_flag_column(self, timeframe_without_core_flag: ts.TimeFrame) -> None:
        """Test that an error is raised if the core flag column is not found."""
        with pytest.raises(ValueError):
            update_corrections_core_flags(timeframe_without_core_flag)


class TestUpdateQualityControlCoreFlags:
    def test_update_quality_control_core_flags(self, sample_container: TimeSeriesContainer) -> None:
        """Test the core flag column is updated with the 'removed' core flag (8),
        and the 'unchecked' core flag (32) is removed."""
        tf = add_initial_core_flags(sample_container).data
        assert tf is not None
        tf = update_quality_control_core_flags(tf)
        flag_col = core_flag_column_name("value")
        # Should be left with missing (4) plus removed (8) flags.
        assert list(tf.df[flag_col]) == [0, 12, 0, 12, 0]

    def test_unchecked_not_removed(self, sample_container: TimeSeriesContainer) -> None:
        """Test that the 'unchecked' flag is not removed when the QC flag is missing."""
        tf = add_initial_core_flags(sample_container).data
        assert tf is not None
        tf = tf.with_df(tf.df.with_columns(pl.Series("value_QC_FLAG", [0, None, 0, None, 0])))
        tf = update_quality_control_core_flags(tf)
        flag_col = core_flag_column_name("value")
        # Should be left with missing (4) plus unchecked (32) flags.
        assert list(tf.df[flag_col]) == [0, 36, 0, 36, 0]

    def test_no_core_flag_column(self, timeframe_without_core_flag: ts.TimeFrame) -> None:
        """Test that an error is raised if the core flag column is not found."""
        with pytest.raises(ValueError):
            update_quality_control_core_flags(timeframe_without_core_flag)


class TestUpdateInfillCoreFlags:
    def test_update_infill_core_flags(self, sample_container: TimeSeriesContainer) -> None:
        """Test that the core flag column is updated with the 'estimated' core flag (2)."""
        tf = add_initial_core_flags(sample_container).data
        assert tf is not None
        tf = update_infill_core_flags(tf)
        flag_col = core_flag_column_name("value")
        assert list(tf.df[flag_col]) == [32, 36, 34, 36, 32]

    def test_no_core_flag_column(self, timeframe_without_core_flag: ts.TimeFrame) -> None:
        """Test that an error is raised if the core flag column is not found."""
        with pytest.raises(ValueError):
            update_infill_core_flags(timeframe_without_core_flag)
