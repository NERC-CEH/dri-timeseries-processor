from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
import time_stream as ts
from time_stream.infill import InfillMethod

from dritimeseriesprocessor.flagging.flagger import add_initial_core_flags
from dritimeseriesprocessor.infilling.infiller import run_infilling


class MockInfillMethod(InfillMethod):
    name = "Mock"

    def __init__(self, **kwargs: Any):
        pass

    def _fill(self, df: pl.DataFrame, infill_column: str) -> pl.DataFrame:
        return df.with_columns(pl.col(infill_column).fill_null(100).alias(f"{infill_column}_{self.name}"))


@pytest.fixture
def ts_ids() -> Dict[str, Any]:
    datetimes = pl.datetime_range(start=datetime(2023, 1, 1), end=datetime(2023, 1, 1, 9), interval="1h", eager=True)
    ta_data = pl.DataFrame(
        {
            "time": datetimes,
            "temperature": [20.0, 21.0, None, None, 22.0, 23.0, None, 24.0, 25.0, 26.0],
        }
    )
    pa_data = pl.DataFrame(
        {
            "time": datetimes,
            "pressure": [1010.0, 1011.0, 1012.0, None, 1013.0, None, 1014.0, 1015.0, None, 1016.0],
        }
    )
    resolution = ts.Period.of_hours(1)
    periodicity = ts.Period.of_hours(1)
    ta_tf = ts.TimeFrame(ta_data, "time", resolution, periodicity).with_metadata({"column_name": "temperature"})
    ta_tf = add_initial_core_flags(ta_tf)

    pa_tf = ts.TimeFrame(pa_data, "time", resolution, periodicity).with_metadata({"column_name": "pressure"})
    pa_tf = add_initial_core_flags(pa_tf)

    ts_ids = {
        "SITE1_ta_30min_raw": SimpleNamespace(data=ta_tf, infill_configs=[]),
        "SITE1_pa_30min_raw": SimpleNamespace(data=pa_tf, infill_configs=[]),
    }
    return ts_ids


@pytest.fixture
def mock_methods_dict() -> Dict[str, Any]:
    # Set up dummy infilling methods
    infill_method1 = type(
        "DummyInfillMethod",
        (),
        {
            "method_id": 1,
            "name": "method1",
            "description": "description of method1",
            "function_name": MockInfillMethod,
        },
    )()

    infill_method2 = type(
        "DummyInfillMethod",
        (),
        {
            "method_id": 2,
            "name": "method2",
            "description": "description of method2",
            "function_name": MockInfillMethod,
        },
    )()

    mock_methods_dict = {
        "method1": infill_method1,
        "method2": infill_method2,
    }
    return mock_methods_dict


@pytest.fixture
def infill_config_1() -> Dict[str, Any]:
    infill_config = type(
        "DummyInfillConfig",
        (),
        {
            "site_id": "SITE1",
            "ts_id": "SITE1_ta_30min_raw",
            "configs": [
                type(
                    "DummyMethodConfig",
                    (),
                    {
                        "name": "method1",
                        "interval": (datetime(2000, 1, 1), None),
                        "observation_interval": (datetime(2023, 1, 1), None),
                        "parameters": {"max_gap_size": 1},
                    },
                )
            ],
            "annotations": {"data-processing-configuration-priority": 1},
        },
    )()
    return infill_config


@pytest.fixture
def infill_config_2() -> Dict[str, Any]:
    infill_config = type(
        "DummyInfillConfig",
        (),
        {
            "site_id": "SITE1",
            "ts_id": "SITE1_ta_30min_raw",
            "configs": [
                type(
                    "DummyMethodConfig",
                    (),
                    {
                        "name": "method2",
                        "interval": (datetime(2000, 1, 1), None),
                        "observation_interval": (datetime(2023, 1, 1), None),
                        "parameters": {"max_gap_size": 3},
                    },
                )
            ],
            "annotations": {"data-processing-configuration-priority": 2},
        },
    )()
    return infill_config


class TestRunInfilling:
    @patch("dritimeseriesprocessor.infilling.infiller.get_infill_methods")
    def test_run_infilling_no_methods(self, mock_get_methods: MagicMock, ts_ids: Dict[str, Any]) -> None:
        """Test run_infilling when no infill methods are defined."""
        mock_get_methods.return_value = {}
        result = run_infilling(ts_ids)

        assert result == ts_ids

    @patch("dritimeseriesprocessor.infilling.infiller.get_infill_methods")
    def test_run_infilling_success(
        self,
        mock_get_methods: MagicMock,
        infill_config_1: Dict[str, Any],
        mock_methods_dict: Dict[str, Any],
        ts_ids: Dict[str, Any],
    ) -> None:
        """Test basic results of run_infilling."""
        for ts_id, ts_container in ts_ids.items():
            ts_container.infill_configs = [infill_config_1]

        mock_get_methods.return_value = mock_methods_dict

        expected_infill_flags = [
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            0,
            0,
            0,
        ]

        # Call function
        result = run_infilling(ts_ids)

        # Check flag system added
        result["SITE1_ta_30min_raw"].data.get_flag_system("infill_flags")

        # Check columns added
        assert "temperature_INFILL_FLAG" in result["SITE1_ta_30min_raw"].data.columns
        # Check flag values (from mock functions) have been added
        assert result["SITE1_ta_30min_raw"].data.df["temperature_INFILL_FLAG"].to_list() == expected_infill_flags

    @patch("dritimeseriesprocessor.infilling.infiller.get_infill_methods")
    def test_run_infilling_multiple_methods(
        self,
        mock_get_methods: MagicMock,
        infill_config_1: Dict[str, Any],
        infill_config_2: Dict[str, Any],
        mock_methods_dict: Dict[str, Any],
        ts_ids: Dict[str, Any],
    ) -> None:
        """Test run_infilling with multiple infill methods for a single column.
        Checks if the methods are applied in the correct order (by priority).
        """
        for ts_id, ts_container in ts_ids.items():
            ts_container.infill_configs = [infill_config_1, infill_config_2]

        mock_get_methods.return_value = mock_methods_dict

        expected_infill_flags = [
            0,
            0,
            2,
            2,
            0,
            0,
            1,
            0,
            0,
            0,
        ]

        # Call function
        result = run_infilling(ts_ids)

        # Check flag system added
        result["SITE1_ta_30min_raw"].data.get_flag_system("infill_flags")

        # Check columns added
        assert "temperature_INFILL_FLAG" in result["SITE1_ta_30min_raw"].data.columns
        # Check flag values (from mock functions) have been added
        assert result["SITE1_ta_30min_raw"].data.df["temperature_INFILL_FLAG"].to_list() == expected_infill_flags
