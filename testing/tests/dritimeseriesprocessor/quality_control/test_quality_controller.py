from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
import time_stream as ts
from polars.testing import assert_frame_equal
from time_stream.qc import QCCheck

from dritimeseriesprocessor.flagging.flagger import add_initial_core_flags
from dritimeseriesprocessor.quality_control.quality_controller import remove_qcd_data, run_quality_control

TA_TS_ID = "SITE1_ta_30min_raw"
PA_TS_ID = "SITE1_pa_30min_raw"


class MockCheck(QCCheck):
    name = "Mock"

    def __init__(self, **kwargs: Any):
        pass

    def expr(self, _ctx: Any, _column: str) -> pl.Expr:
        return pl.lit(True)


@pytest.fixture
def ts_ids() -> Dict[str, Any]:
    data = pl.DataFrame(
        {
            "time": [
                datetime(2023, 8, 10),
                datetime(2023, 8, 11),
                datetime(2023, 8, 12),
                datetime(2023, 8, 13),
                datetime(2023, 8, 14),
                datetime(2023, 8, 15),
            ],
            "value": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        }
    )

    resolution = ts.Period.of_days(1)
    periodicity = ts.Period.of_days(1)
    tf = ts.TimeFrame(data, "time", resolution, periodicity).with_metadata({"site_id": "SITE1", "column_name": "value"})
    tf = add_initial_core_flags(tf)

    ts_ids = {
        "SITE1_ta_30min_raw": SimpleNamespace(data=tf, qc_configs=[]),
        "SITE1_pa_30min_raw": SimpleNamespace(data=tf, qc_configs=[]),
    }

    return ts_ids


@pytest.fixture
def mock_methods_dict() -> Dict[str, Any]:
    QC_method1 = type(
        "DummyQCMethod",
        (),
        {
            "method_id": 1,
            "name": "Mock Check 1",
            "description": "A mock qc check",
            "function_name": MockCheck,
            "method_type": "quality_control",
            "arg_mapping": {},
            "kwargs": {},
        },
    )()

    QC_method2 = type(
        "DummyQCMethod",
        (),
        {
            "method_id": 2,
            "name": "Mock Check 2",
            "description": "Another mock qc check",
            "function_name": MockCheck,
            "method_type": "quality_control",
            "arg_mapping": {},
            "kwargs": {},
        },
    )()

    QC_method3 = type(
        "DummyQCMethod",
        (),
        {
            "method_id": 4,
            "name": "Mock Check 3",
            "description": "Another mock qc check",
            "function_name": MockCheck,
            "method_type": "quality_control",
            "arg_mapping": {},
            "kwargs": {},
        },
    )()

    mock_methods_dict = {
        "mock_check1": QC_method1,
        "mock_check2": QC_method2,
        "mock_check3": QC_method3,
    }

    return mock_methods_dict


@pytest.fixture
def qc_config_1() -> Dict[str, Any]:
    qc_config = type(
        "DummyQCConfig",
        (),
        {
            "site_id": "SITE1",
            "ts_id": TA_TS_ID,
            "configs": [
                type(
                    "DummyMethodConfig",
                    (),
                    {
                        "name": "mock_check1",
                        "interval": (datetime(2000, 1, 1), None),
                        "observation_interval": (datetime(2023, 1, 1), None),
                        "parameters": {
                            "arg1": -40,
                            "arg2": 40,
                        },
                    },
                )
            ],
            "annotations": {},
        },
    )()

    return qc_config


@pytest.fixture
def qc_config_2() -> Dict[str, Any]:
    qc_config = type(
        "DummyQCConfig",
        (),
        {
            "site_id": "SITE1",
            "ts_id": PA_TS_ID,
            "configs": [
                type(
                    "DummyMethodConfig",
                    (),
                    {
                        "name": "mock_check2",
                        "interval": (datetime(2000, 1, 1), None),
                        "observation_interval": (datetime(2023, 1, 1), None),
                        "parameters": {
                            "arg1": 20,
                            "arg2": 400,
                        },
                    },
                )
            ],
            "annotations": {},
        },
    )()

    return qc_config


@pytest.fixture
def qc_config_3() -> Dict[str, Any]:
    qc_config = type(
        "DummyQCConfig",
        (),
        {
            "site_id": "SITE1",
            "ts_id": PA_TS_ID,
            "configs": [
                type(
                    "DummyMethodConfig",
                    (),
                    {
                        "name": "mock_check3",
                        "interval": (datetime(2000, 1, 1), None),
                        "observation_interval": (datetime(2023, 8, 11), datetime(2023, 8, 13)),
                        "parameters": {
                            "arg1": 20,
                            "arg2": 400,
                        },
                    },
                )
            ],
            "annotations": {},
        },
    )()
    return qc_config


class TestRemoveQCdData:
    """Unit tests for the remove_qcd_data function."""

    def test_remove_qcd_data(self) -> None:
        """
        Test that remove_qcd_data correctly removes QC'd data.
        """
        df = pl.DataFrame({"data": [1, 2, 3, 4, 5], "qc_flag": [0, 1, 0, 1, 0]})

        result = remove_qcd_data(df, "data", "qc_flag")
        expected = pl.DataFrame({"data": [1, None, 3, None, 5], "qc_flag": [0, 1, 0, 1, 0]})
        assert_frame_equal(result, expected)

    def test_no_qc_flags(self) -> None:
        """
        Test that remove_qcd_data returns the original dataframe when there are no QC flags.
        """
        df_no_flags = pl.DataFrame({"data": [1, 2, 3, 4, 5], "qc_flag": [0, 0, 0, 0, 0]})
        result = remove_qcd_data(df_no_flags, "data", "qc_flag")

        assert_frame_equal(result, df_no_flags)

    def test_all_qc_flags(self) -> None:
        """
        Test that remove_qcd_data returns a dataframe with all None values in the data column when all QC flags are set.
        """
        df_all_flags = pl.DataFrame({"data": [1, 2, 3, 4, 5], "qc_flag": [1, 1, 1, 1, 1]})
        result = remove_qcd_data(df_all_flags, "data", "qc_flag")
        expected = pl.DataFrame(
            {"data": [None, None, None, None, None], "qc_flag": [1, 1, 1, 1, 1]},
            schema={"data": pl.Int64, "qc_flag": pl.Int64},
        )

        assert_frame_equal(result, expected)


class TestRunQualityControl:
    @patch("dritimeseriesprocessor.quality_control.quality_controller.get_qc_methods")
    def test_run_quality_control_no_methods(self, mock_get_methods: MagicMock, ts_ids: Dict[str, Any]) -> None:
        """Test run_quality_control when no QC methods are defined."""
        mock_get_methods.return_value = {}
        result = run_quality_control(ts_ids)

        assert result == ts_ids

    @patch("dritimeseriesprocessor.quality_control.quality_controller.get_qc_methods")
    def test_run_quality_control_success(
        self,
        mock_get_methods: MagicMock,
        ts_ids: Dict[str, Any],
        mock_methods_dict: Dict[str, Any],
        qc_config_1: Dict[str, Any],
    ) -> None:
        """Test basic results of run_quality_control."""
        for ts_id, ts_container in ts_ids.items():
            ts_container.qc_configs = [qc_config_1]

        mock_get_methods.return_value = mock_methods_dict

        # Call function
        result = run_quality_control(ts_ids)

        # Check flag system added
        result[TA_TS_ID].data.get_flag_system("qc_flags")
        # Check columns added
        assert "value_QC_FLAG" in result[TA_TS_ID].data.columns
        # Check flag values (from mock functions) have been added
        assert result[TA_TS_ID].data.df["value_QC_FLAG"].to_list() == [1, 1, 1, 1, 1, 1]

    @patch("dritimeseriesprocessor.quality_control.quality_controller.get_qc_methods")
    def test_run_quality_control_multiple_methods(
        self,
        mock_get_methods: MagicMock,
        ts_ids: Dict[str, Any],
        mock_methods_dict: Dict[str, Any],
        qc_config_1: Dict[str, Any],
        qc_config_2: Dict[str, Any],
    ) -> None:
        """Test run_quality_control with multiple QC methods for a single column.
        Checks if the methods are applied in the correct order (by priority).
        """
        for ts_id, ts_container in ts_ids.items():
            ts_container.qc_configs = [qc_config_1, qc_config_2]

        mock_get_methods.return_value = mock_methods_dict

        # Call function
        result = run_quality_control(ts_ids)

        # Check flag system added
        result[TA_TS_ID].data.get_flag_system("qc_flags")
        # Check columns added
        assert "value_QC_FLAG" in result[TA_TS_ID].data.columns
        # Check flag values (from both mock functions) have been added
        assert result[TA_TS_ID].data.df["value_QC_FLAG"].to_list() == [3, 3, 3, 3, 3, 3]

    @patch("dritimeseriesprocessor.quality_control.quality_controller.get_qc_methods")
    def test_run_quality_control_observation_interval(
        self,
        mock_get_methods: MagicMock,
        ts_ids: Dict[str, Any],
        mock_methods_dict: Dict[str, Any],
        qc_config_3: Dict[str, Any],
    ) -> None:
        """Test run_quality_control that has an observation interval - meaning that only data for a specific date
        range should be flagged
        """
        for ts_id, ts_container in ts_ids.items():
            ts_container.qc_configs = [qc_config_3]

        mock_get_methods.return_value = mock_methods_dict

        # Call function
        result = run_quality_control(ts_ids)

        # Check flag system added
        result[TA_TS_ID].data.get_flag_system("qc_flags")
        # Check columns added
        assert "value_QC_FLAG" in result[TA_TS_ID].data.columns
        # Check flag values (from both mock functions) have been added
        assert result[TA_TS_ID].data.df["value_QC_FLAG"].to_list() == [0, 4, 4, 4, 0, 0]
