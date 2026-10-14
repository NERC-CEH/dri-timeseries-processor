from datetime import datetime

import polars as pl
import pytest
import time_stream as ts
from tests.utils.data_creation import make_time_series_container

from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.flags.flag_methods import (
    add_initial_core_flags,
    ensure_flag_column,
    initialise_flag_systems,
    update_corrections_core_flags,
    update_infill_core_flags,
    update_quality_control_core_flags,
)
from dritimeseriesprocessor.utils.enums import FlagRole

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

# Flag column names deliberately don't start with the data column name ("value"), as the metadata is free to name
# them anything.
CORE_FLAG_COL = "level_CORE_FLAG"
CORRS_FLAG_COL = "level_CORRS_FLAG"
QC_FLAG_COL = "level_QC_FLAG"
INFILL_FLAG_COL = "level_INFILL_FLAG"

# Maps each flag column to the flag system that governs it, as the metadata would define for a dataset.
FLAG_COLUMN_SCHEMES = {
    CORE_FLAG_COL: "core_flags",
    CORRS_FLAG_COL: "corrs_flags",
    QC_FLAG_COL: "qc_flags",
    INFILL_FLAG_COL: "infill_flags",
}

FLAG_COLUMN_ROLES = {
    FlagRole.CORE: CORE_FLAG_COL,
    FlagRole.CORRECTION: CORRS_FLAG_COL,
    FlagRole.QUALITY_CONTROL: QC_FLAG_COL,
    FlagRole.INFILL: INFILL_FLAG_COL,
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
    tf.metadata["column_name"] = "value"
    tf.register_flag_system("corrs_flags", {"ADD": 1})
    tf.init_flag_column("corrs_flags", CORRS_FLAG_COL, [1, 0, 0, 0, 1])
    tf.register_flag_system("qc_flags", {"RANGE": 1})
    tf.init_flag_column("qc_flags", QC_FLAG_COL, [0, 1, 0, 1, 0])
    tf.register_flag_system("infill_flags", {"INTERP": 1})
    tf.init_flag_column("infill_flags", INFILL_FLAG_COL, [0, 0, 1, 0, 0])

    container = make_time_series_container("test")
    container.data = tf
    container.flag_column_schemes = dict(FLAG_COLUMN_SCHEMES)
    container.flag_column_roles = dict(FLAG_COLUMN_ROLES)

    # Set up the core flag system and column, as the processor does before applying core flags.
    initialise_flag_systems(container, FLAG_SYSTEMS)

    return container


@pytest.fixture
def sample_timeframe(sample_container: TimeSeriesContainer) -> ts.TimeFrame:
    """The sample container's TimeFrame, with the initial core flags added."""
    tf = add_initial_core_flags(sample_container).data
    assert tf is not None
    return tf


class TestAddInitialCoreFlags:
    def test_add_initial_core_flags(self, sample_container: TimeSeriesContainer) -> None:
        """Tests that the initial core flags of 'unchecked' (32) and 'missing' (4) are added correctly."""
        container = add_initial_core_flags(sample_container)
        tf = container.data
        assert tf is not None

        assert CORE_FLAG_COL in tf.flag_columns
        assert list(tf.df[CORE_FLAG_COL]) == [32, 36, 32, 36, 32]

    def test_no_core_flag_column(self, sample_container: TimeSeriesContainer) -> None:
        """Tests that nothing is added when the dataset has no core flag column."""
        sample_container.flag_column_roles = {}
        container = add_initial_core_flags(sample_container)
        assert container.data is not None
        assert list(container.data.df[CORE_FLAG_COL]) == [0, 0, 0, 0, 0]


class TestUpdateCorrectionsCoreFlags:
    def test_update_corrections_core_flags(self, sample_timeframe: ts.TimeFrame) -> None:
        """Tests that the core flag column is updated with 'corrected' core flag (1)."""
        tf = update_corrections_core_flags(sample_timeframe, CORE_FLAG_COL, CORRS_FLAG_COL)
        assert list(tf.df[CORE_FLAG_COL]) == [33, 36, 32, 36, 33]

    def test_no_corrections_flag_column(self, sample_timeframe: ts.TimeFrame) -> None:
        """Tests that the core flags are left unchanged when the dataset has no corrections flag column."""
        tf = update_corrections_core_flags(sample_timeframe, CORE_FLAG_COL, None)
        assert list(tf.df[CORE_FLAG_COL]) == [32, 36, 32, 36, 32]


class TestUpdateQualityControlCoreFlags:
    def test_unchecked_flag_cleared_without_adding_removed(self, sample_timeframe: ts.TimeFrame) -> None:
        """Tests that the 'unchecked' core flag (32) is cleared and no 'removed' core flag (8) is added."""
        tf = update_quality_control_core_flags(sample_timeframe, CORE_FLAG_COL, QC_FLAG_COL)
        # Rows 1 and 3 failed QC but were already null, so they are left with only the missing (4) flag.
        assert list(tf.df[CORE_FLAG_COL]) == [0, 4, 0, 4, 0]

    def test_unchecked_not_removed(self, sample_timeframe: ts.TimeFrame) -> None:
        """Tests that the 'unchecked' flag is not removed when the QC flag is missing."""
        tf = sample_timeframe.with_df(sample_timeframe.df.with_columns(pl.Series(QC_FLAG_COL, [0, None, 0, None, 0])))
        tf = update_quality_control_core_flags(tf, CORE_FLAG_COL, QC_FLAG_COL)
        # Should be left with missing (4) plus unchecked (32) flags.
        assert list(tf.df[CORE_FLAG_COL]) == [0, 36, 0, 36, 0]

    def test_other_core_flags_kept(self, sample_timeframe: ts.TimeFrame) -> None:
        """Tests that other core flags, such as 'corrected' (1), are kept when 'unchecked' is cleared."""
        # Mark a value that failed QC, and a value that passed, as corrected.
        sample_timeframe.add_flag(CORE_FLAG_COL, "corrected", pl.Series([False, True, True, False, False]))
        tf = update_quality_control_core_flags(sample_timeframe, CORE_FLAG_COL, QC_FLAG_COL)
        # Row 1 keeps corrected (1) alongside missing (4). Row 2 keeps corrected (1).
        assert list(tf.df[CORE_FLAG_COL]) == [0, 5, 1, 4, 0]

    def test_no_qc_flag_column(self, sample_timeframe: ts.TimeFrame) -> None:
        """Tests that the core flags are left unchanged when the dataset has no QC flag column."""
        tf = update_quality_control_core_flags(sample_timeframe, CORE_FLAG_COL, None)
        assert list(tf.df[CORE_FLAG_COL]) == [32, 36, 32, 36, 32]


class TestUpdateInfillCoreFlags:
    def test_update_infill_core_flags(self, sample_timeframe: ts.TimeFrame) -> None:
        """Tests that the core flag column is updated with the 'estimated' core flag (2)."""
        tf = update_infill_core_flags(sample_timeframe, CORE_FLAG_COL, INFILL_FLAG_COL)
        assert list(tf.df[CORE_FLAG_COL]) == [32, 36, 34, 36, 32]

    def test_no_infill_flag_column(self, sample_timeframe: ts.TimeFrame) -> None:
        """Tests that the core flags are left unchanged when the dataset has no infill flag column."""
        tf = update_infill_core_flags(sample_timeframe, CORE_FLAG_COL, None)
        assert list(tf.df[CORE_FLAG_COL]) == [32, 36, 32, 36, 32]


class TestEnsureFlagColumn:
    def test_skips_column_not_in_schemes(self) -> None:
        """Tests that nothing is set up when the dataset does not declare the flag column."""
        tf = ts.TimeFrame(sample_dataframe(), time_name="timestamp")

        ensure_flag_column(tf, "value_CORE_FLAG", {"core_flags": {"unchecked": 32}}, {})

        assert "value_CORE_FLAG" not in tf.flag_columns
        assert "core_flags" not in tf.flag_systems

    def test_registers_system_and_inits_column(self) -> None:
        """Tests that the flag system is registered and the flag column created when neither exists."""
        tf = ts.TimeFrame(sample_dataframe(), time_name="timestamp")

        ensure_flag_column(tf, "value_CORE_FLAG", {"core_flags": {"unchecked": 32}}, {"value_CORE_FLAG": "core_flags"})

        assert "core_flags" in tf.flag_systems
        assert "value_CORE_FLAG" in tf.flag_columns

    def test_leaves_existing_flag_column_untouched(self) -> None:
        """Tests that an existing flag column keeps its values and is not re-initialised."""
        tf = ts.TimeFrame(sample_dataframe(), time_name="timestamp")
        tf.register_flag_system("core_flags", {"unchecked": 32})
        tf.init_flag_column("core_flags", "value_CORE_FLAG", [32, 0, 0, 0, 0])

        ensure_flag_column(tf, "value_CORE_FLAG", {"core_flags": {"unchecked": 32}}, {"value_CORE_FLAG": "core_flags"})

        assert list(tf.df["value_CORE_FLAG"]) == [32, 0, 0, 0, 0]
