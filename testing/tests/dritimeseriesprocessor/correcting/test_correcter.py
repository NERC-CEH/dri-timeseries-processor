from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict
from unittest import mock

import polars as pl
import pytest
import time_stream as ts
from driutils.metadata_api.api_manager import MetadataAPIManager
from driutils.testing_utils.mock_metadata_api import MockMetadataAPI

from dritimeseriesprocessor.correcting.correcter import run_corrections, update_config_item_with_site_attributes
from dritimeseriesprocessor.flagging.flagger import add_initial_core_flags
from metadata_manager.models.schemas.data_processing_configurations import ConfigItem, DataProcessingConfiguration
from testing.utils.base_test_helper import BaseTestHelper


def create_test_tf(col_name: str, datetimes: list, data: list, periodicity: ts.Period) -> ts.TimeFrame:
    """Set up test fixtures."""
    df = pl.DataFrame({"time": datetimes, col_name: data})

    tf = ts.TimeFrame(df, "time", periodicity, periodicity).with_metadata({"site_id": "site1", "column_name": col_name})
    tf = add_initial_core_flags(tf)

    return tf


@pytest.fixture()
def mock_methods_dict() -> Dict[str, Any]:
    lw_corr = type(
        "DummyCorrectionMethod",
        (),
        {
            "method_id": 1,
            "name": "LW_CORR",
            "description": "Correction for long wave radiation",
            "function_name": "lw_corr",
            "method_type": "correction",
            "arg_mapping": {"lwout_unc": "lw_unc", "lwin_unc": "lw_unc"},
        },
    )()

    scalar = type(
        "DummyCorrectionMethod",
        (),
        {
            "method_id": 2,
            "name": "SCALAR",
            "description": "Scale the data point by a correction factor",
            "function_name": "scalar",
            "method_type": "correction",
            "arg_mapping": {},
        },
    )()

    mock_methods_dict = {
        "lw_corr": lw_corr,
        "scalar": scalar,
    }
    return mock_methods_dict


class TestRunCorrections:
    """
    Test suite for the run_corrections function.
    """

    @mock.patch("dritimeseriesprocessor.correcting.correcter.get_correction_methods")
    def test_run_corrections_basic(
        self,
        mock_get_methods: mock.MagicMock,
        mock_methods_dict: Dict[str, Any],
    ) -> None:
        """
        Test basic functionality of run_corrections.
        Checks if the function adds the flag system, adds the flag columns, and runs the correction method.
        """
        g1_ts = create_test_tf(
            "g1",
            [
                datetime(2017, 11, 10, 11),
                datetime(2017, 11, 10, 11, 30),  # Config start date
                datetime(2017, 11, 10, 12),
                datetime(2017, 11, 10, 12, 30),
                datetime(2017, 11, 10, 13),
            ],
            [7.88732, 15.89324, 15.68856, 16.91815, 14.77755],
            ts.Period.of_minutes(30),
        )
        g1_ts_id = "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-g1_30min_raw"
        ts_ids = {
            g1_ts_id: SimpleNamespace(
                data=g1_ts,
                correction_configs=[
                    DataProcessingConfiguration.model_construct(
                        site_id="http://fdri.ceh.ac.uk/id/site/cosmos-alic1",
                        ts_id="http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-g1_30min_raw",
                        annotations={},
                        configs=[
                            ConfigItem.model_construct(
                                name="scalar",
                                interval=(datetime(1800, 1, 1, 0, 0), None),
                                observation_interval=(
                                    datetime(2017, 11, 10, 11, 30),
                                    datetime(2017, 11, 11, 0, 0),
                                ),
                                parameters={"correction_factor": 0.1986},
                            )
                        ],
                    ),
                ],
            )
        }

        mock_get_methods.return_value = mock_methods_dict

        result = run_corrections(ts_ids)

        # Check flag system added
        result[g1_ts_id].data.get_flag_system("corrs_flags")
        # Check columns added
        assert "g1_CORRS_FLAG" in result[g1_ts_id].data.columns
        # Check the correction method has been applied
        assert result[g1_ts_id].data.df["g1"].to_list() == [
            7.88732,
            3.156397464,
            3.115748016,
            3.35994459,
            2.93482143,
        ]

        # Check CORRS flag values have been added
        assert result[g1_ts_id].data.df["g1_CORRS_FLAG"].to_list() == [0, 2, 2, 2, 2]
        # Check core flag values updated
        assert result[g1_ts_id].data.df["g1_CORE_FLAG"].to_list() == [32, 33, 33, 33, 33]

    @mock.patch("dritimeseriesprocessor.correcting.correcter.get_correction_methods")
    def test_run_corrections_with_arg_mapping(
        self,
        mock_get_methods: mock.MagicMock,
        base_test_helper: BaseTestHelper,
        mock_methods_dict: Dict[str, Any],
    ) -> None:
        """
        Test basic functionality with LW_CORR method which uses argument mapping.
        """
        datetimes = [
            datetime(2018, 12, 20, 11),
            datetime(2018, 12, 20, 11, 30),
            datetime(2018, 12, 20, 12, 0),
            datetime(2018, 12, 20, 12, 30),  # config end date
            datetime(2018, 12, 20, 13, 0),
        ]

        lwout_ts = create_test_tf("lwout", datetimes, [None, None, 361.4, 361.4, 360.6], ts.Period.of_minutes(30))
        lwout_unc_ts = create_test_tf(
            "lwout_unc", datetimes, [None, None, -2.898, -3.535, -4.91], ts.Period.of_minutes(30)
        )
        ta_ts = create_test_tf("ta", datetimes, [8.9, 9.11, 9.35, 9.45, 9.37], ts.Period.of_minutes(30))
        lwout_ts_id = "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-lwout_30min_raw"
        lwout_unc_ts_id = "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-lwout_unc_30min_raw"
        ta_ts_id = "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-ta_30min_raw"

        ts_ids = {
            lwout_ts_id: SimpleNamespace(
                data=lwout_ts,
                correction_configs=[
                    DataProcessingConfiguration.model_construct(
                        site_id="http://fdri.ceh.ac.uk/id/site/cosmos-alic1",
                        ts_id="http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-lwout_30min_raw",
                        annotations={},
                        configs=[
                            ConfigItem.model_construct(
                                name="lw_corr",
                                interval=(datetime(1800, 1, 1, 0, 0), None),
                                observation_interval=(datetime(2016, 7, 28, 15, 0), datetime(2018, 12, 20, 12, 30)),
                                parameters={
                                    "dep_ts": ["COSMOS-ALIC1-TA_30MIN_RAW", "COSMOS-ALIC1-LWOUT_UNC_30MIN_RAW"],
                                    "correction_factor": 1.0337,
                                },
                            )
                        ],
                    )
                ],
            ),
            lwout_unc_ts_id: SimpleNamespace(data=lwout_unc_ts, correction_configs=[]),
            ta_ts_id: SimpleNamespace(data=ta_ts, correction_configs=[]),
        }

        mock_get_methods.return_value = mock_methods_dict

        result = run_corrections(ts_ids)

        # Test lw_corr has been applied to lwout. This uses the argument mapping to map lwout_unc to lw_unc
        result[lwout_ts_id].data.get_flag_system("corrs_flags")

        # Check columns added
        assert "lwout_CORRS_FLAG" in result[lwout_ts_id].data.columns
        # Check the correction method has been applied
        assert result[lwout_ts_id].data.df["lwout"].to_list() == [
            None,
            None,
            358.12876586484373,
            357.98189715415776,
            360.6,
        ]

        # Check CORRS flag values have been added - Not flagged None values
        assert result[lwout_ts_id].data.df["lwout_CORRS_FLAG"].to_list() == [0, 0, 1, 1, 0]
        # Check core flag values updated - None values left with missing flag (32 + 4)
        assert result[lwout_ts_id].data.df["lwout_CORE_FLAG"].to_list() == [36, 36, 33, 33, 32]

    @mock.patch("dritimeseriesprocessor.correcting.correcter.get_correction_methods")
    def test_run_corrections_no_config(
        self,
        mock_get_methods: mock.MagicMock,
        mock_methods_dict: Dict[str, Any],
    ) -> None:
        """
        Test run_corrections when no corrections config is available.
        Checks if the function returns the original DataFrame unchanged.
        """
        # Create data with no corresponding correction config
        ta_ts = create_test_tf(
            "ta",
            [
                datetime(2024, 11, 10, 11),
                datetime(2024, 11, 10, 11, 30),
                datetime(2024, 11, 10, 12),
                datetime(2024, 11, 10, 12, 30),
                datetime(2024, 11, 10, 13),
            ],
            [1, 2, 3, 4, 5],
            ts.Period.of_minutes(30),
        )
        ts_ids = {
            "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-ta_30min_raw": SimpleNamespace(
                data=ta_ts, correction_configs=[]
            ),
        }

        mock_get_methods.return_value = mock_methods_dict

        result = run_corrections(ts_ids)

        assert result == ts_ids

    @mock.patch.object(MetadataAPIManager, "_make_api_call")
    @mock.patch("dritimeseriesprocessor.correcting.correcter.get_correction_methods")
    def test_run_corrections_no_methods(
        self,
        mock_get_methods: mock.MagicMock,
        mock_api_manager: mock.MagicMock,
        base_test_helper: BaseTestHelper,
    ) -> None:
        """
        Test run_corrections when corrections config exists but no methods are specified.
        Checks if the function returns the original DataFrame unchanged.
        """
        g1_ts = create_test_tf(
            "g1",
            [
                datetime(2017, 11, 10, 11),
                datetime(2017, 11, 10, 11, 30),  # Config start date
                datetime(2017, 11, 10, 12),
                datetime(2017, 11, 10, 12, 30),
                datetime(2017, 11, 10, 13),
            ],
            [7.88732, 15.89324, 15.68856, 16.91815, 14.77755],
            ts.Period.of_minutes(30),
        )
        g1_ts_id = "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-g1_30min_raw"
        ts_ids = {
            g1_ts_id: {
                "data": g1_ts,
            }
        }

        mock_api_manager.side_effect = MockMetadataAPI(api_data=base_test_helper.create_all_metadata_api_data())
        mock_get_methods.return_value = {}

        result = run_corrections(ts_ids)

        assert result == ts_ids


@mock.patch.object(MetadataAPIManager, "_make_api_call")
class TestUpdateConfigItemsWithSiteAttributes:
    def test_update_config_item_with_site_attribute(self, mock_metadata_api: mock.MagicMock) -> None:
        response_data = {
            "meta": {},
            "items": [{"@id": "http://fdri.ceh.ac.uk/id/site/cosmos-hollin", "altitude": 123.45}],
        }
        mock_api_data = {"https://dri-metadata-api.staging.eds.ceh.ac.uk/id/site/cosmos-holln": response_data}
        mock_metadata_api.side_effect = MockMetadataAPI(api_data=mock_api_data)

        config_item = ConfigItem.model_construct(
            name="pa_corr",
            interval=(datetime(1800, 1, 1, 0, 0), None),
            observation_interval=(datetime(2021, 10, 1, 0, 30), datetime(2021, 11, 1, 0, 0)),
            parameters={"dep_ts": "COSMOS-HOLLN-TA_30MIN_RAW", "correction_factor": -2.5, "site_attribute": "ALTITUDE"},
        )

        expected_config = ConfigItem.model_construct(
            name="pa_corr",
            interval=(datetime(1800, 1, 1, 0, 0), None),
            observation_interval=(datetime(2021, 10, 1, 0, 30), datetime(2021, 11, 1, 0, 0)),
            parameters={"dep_ts": "COSMOS-HOLLN-TA_30MIN_RAW", "correction_factor": -2.5, "altitude": 123.45},
        )

        updated_config = update_config_item_with_site_attributes(
            config_item=config_item, site_id="http://fdri.ceh.ac.uk/id/site/cosmos-holln"
        )
        assert updated_config == expected_config
