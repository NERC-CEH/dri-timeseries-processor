import json
import os
import shutil
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Union

import polars as pl
from polars.testing import assert_frame_equal
from time_stream import TimeSeries


class ComparisonError(Exception):
    pass

def load_json(json_path: str) -> Dict[str, Any]:
    with open(json_path) as json_file:
        return json.load(json_file)


class TestHelper(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()

        self.data_dir = Path(__file__).parents[1].joinpath("data")
        self.input_dir = self.data_dir.joinpath("inputs")
        self.output_dir = self.data_dir.joinpath("outputs")
        self.temp_dir = self.data_dir.joinpath("temp")

        self.original_cwd = os.getcwd()

        self.reset_temp_dir()

        # Set the current working directory to be the temp dir so that all test outputs are written there
        os.chdir(self.temp_dir)
        print()
        pass

    def tearDown(self) -> None:
        super().tearDown()

        self.reset_temp_dir()

        # Reset the current working directory
        os.chdir(self.original_cwd)

    def reset_temp_dir(self) -> None:
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

        self.temp_dir.mkdir(parents=True, exist_ok=True)

    @property
    def metadata_api_data(self) -> Dict[str, Dict[str, Any]]:
        return {
            "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/network/cosmos": load_json(
                self.input_dir.joinpath("mock_metadata_api", "sites_metadata.json")
            ),
            "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset": load_json(
                self.input_dir.joinpath("mock_metadata_api", "ts_id_metadata_alic1.json")
            ),
            "https://dri-metadata-api.staging.eds.ceh.ac.uk/ref/time-series-definition": load_json(
                self.input_dir.joinpath("mock_metadata_api", "ts_def_metadata.json")
            ),
        }

    def load_ts_ids_from_json_file(self, json_path: str) -> Dict[str, Dict[str, Union[str, TimeSeries]]]:
        with open(json_path) as json_file:
            json_data = json.load(json_file)

        ts_ids = self.load_ts_ids_from_dict(json_data)

        return ts_ids

    @staticmethod
    def load_ts_ids_from_dict(
        ts_ids: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Union[str, TimeSeries]]]:
        processed_ts_ids = {}
        for ts_id, ts_metadata in ts_ids.items():
            if ts_metadata.get("data"):
                data_dict = ts_metadata["data"]
                data_dict["time"] = [datetime.fromisoformat(item) for item in data_dict["time"]]
                ts = TimeSeries(
                    df=pl.from_dict(data_dict),
                    time_name="time",
                    resolution=ts_metadata["resolution"],
                    periodicity=ts_metadata["periodicity"],
                    metadata={
                        "site_id": ts_metadata["sourceSite"],
                        "column_name": ts_metadata["sourceColumnName"],
                        "processing_level": ts_metadata["processing_level"],
                    },
                )
                ts_metadata["data"] = ts

            processed_ts_ids[ts_id] = ts_metadata

        return processed_ts_ids

    @staticmethod
    def convert_ts_ids_to_dict(ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]]) -> Dict[str, Dict[str, Any]]:
        # Copy the ts_ids to ensure the source dictionary isn't accidentally modified
        ts_ids = ts_ids.copy()

        output_data = {}

        for ts_id, ts_metadata in ts_ids.items():
            data = ts_metadata.get("data")
            if data:
                ts_metadata["data"] = {
                    "time": data.df["time"].cast(pl.String).to_list(),
                } | {
                    column_name: data.df[column_name].to_list()
                    for column_name in data.df.columns
                    if column_name != "time"
                }

            output_data[ts_id] = ts_metadata

        return output_data

    def compare_ts_ids(
        self,
        expected_ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]],
        actual_ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]],
    ) -> None:
        for expected_ts_id, expected_ts_dict in expected_ts_ids.items():
            actual_ts_dict = actual_ts_ids.get(expected_ts_id)
            if not actual_ts_dict:
                raise ComparisonError(f"The expected time series ID: `{expected_ts_id}` could not be found.")

            for expected_key, expected_value in expected_ts_dict.items():
                actual_value = actual_ts_dict.get(expected_key)
                if actual_value is None and expected_value is not None:
                    raise ComparisonError(
                        f"The expected key `{expected_key}` could not be found for time series ID: `{expected_ts_id}`"
                    )

                # TimeSeries objects require custom comparison to ensure all attributes are compared correctly.
                if isinstance(expected_value, TimeSeries):
                    self.compare_timeseries_objects(expected_timeseries=expected_value, actual_timeseries=actual_value)
                    continue

                # Sort any lists to be compared to ensure the comparison is consistent
                if isinstance(expected_value, list):
                    expected_value = sorted(expected_value)
                    actual_value = sorted(actual_value)

                if expected_value != actual_value:
                    raise ComparisonError(
                        f"The expected and actual values for key `{expected_key}` (ts_id: {expected_ts_id}) do not "
                        f"match. Expected value: `{expected_value}. Actual value: `{actual_value}`"
                    )

    @staticmethod
    def compare_timeseries_objects(expected_timeseries: TimeSeries, actual_timeseries: TimeSeries) -> None:
        # Check the polars dataframes match
        assert_frame_equal(expected_timeseries.df, actual_timeseries.df)

        timeseries_attributes = []
        for attribute_name in timeseries_attributes:
            expected_value = getattr(expected_timeseries, "resolution")
            actual_value = getattr(actual_timeseries, "resolution")
            if expected_value != actual_value:
                raise ComparisonError(
                    f"The expected TimeSeries attribute value for `{attribute_name}` does not match. "
                    f"Expected value: `{expected_value}. Actual value: `{actual_value}`"
                )
