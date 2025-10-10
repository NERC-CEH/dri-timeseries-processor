import json
from datetime import datetime
from typing import Any, Dict, List

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.timeseries_container import TimeseriesContainer
from testing.utils.base_test_helper import BaseTestHelper, ComparisonError


class TimeSeriesTestHelper(BaseTestHelper):
    def load_ts_ids_from_json_file(self, json_path: str) -> Dict[str, TimeseriesContainer]:
        """
        Loads time series id metadata (to be converted to a TimeSeriesContainer object) from a json file, iterating
        over each item to create the relevant ts.TimeFrame objects for any items which contain data attributes.

        Args:
            json_path: Path to load the time series id metadata dictionaries from.

        Returns:
            Dictionary of time series ids and their metadata

        """
        with open(json_path) as json_file:
            json_data = json.load(json_file)

        ts_ids = self.load_ts_ids_from_dict(json_data)

        return ts_ids

    @staticmethod
    def load_ts_ids_from_dict(
        ts_ids: Dict[str, Dict[str, Any]],
    ) -> Dict[str, TimeseriesContainer]:
        """
        Loads time series id metadata (to be converted to a TimeSeriesContainer object) from a dictionary, iterating
        over each item to create the relevant ts.TimeFrame objects for any items which contain data attributes.

        Args:
            ts_ids: Dictionary containing the time series metdata to reformat and create TimeSeriesObjects from.

        Returns:
            Dictionary of time series ids and their metadata.
        """
        processed_ts_ids = {}
        for ts_id, ts_metadata in ts_ids.items():
            if ts_metadata.get("data"):
                data_dict = ts_metadata["data"]
                data_dict["time"] = [datetime.fromisoformat(item) for item in data_dict["time"]]
                tf = ts.TimeFrame(
                    df=pl.from_dict(data_dict),
                    time_name="time",
                    resolution=ts_metadata["resolution"],
                    periodicity=ts_metadata["periodicity"],
                ).with_metadata(
                    {
                        "site_id": ts_metadata["sourceSite"],
                        "column_name": ts_metadata["sourceColumnName"],
                        "processing_level": ts_metadata["processing_level"],
                    }
                )
                ts_metadata["data"] = tf

            processed_ts_ids[ts_id] = TimeseriesContainer(**ts_metadata)

        return processed_ts_ids

    @staticmethod
    def convert_ts_ids_to_dict(ts_ids: Dict[str, TimeseriesContainer]) -> Dict[str, Dict[str, Any]]:
        """
        Convert a dictionary of timeseries ids (containing ts.TimeFrame data objects) into a dictionary that is easily
        written to a json file.

        Args:
            ts_ids: Dictionary of time series id metadata.

        Returns:
            Reformatted dictionary of timeseries id metadata.

        """
        # Copy the ts_ids to ensure the source dictionary isn't accidentally modified
        ts_ids = ts_ids.copy()

        output_data = {}

        for ts_id, ts_metadata in ts_ids.items():
            data = ts_metadata.data
            if data:
                ts_metadata.data = {
                    "time": data.df["time"].cast(pl.String).to_list(),
                } | {
                    column_name: data.df[column_name].to_list()
                    for column_name in data.df.columns
                    if column_name != "time"
                }

            output_data[ts_id] = ts_metadata.__dict__

        return output_data

    def compare_ts_ids(
        self,
        expected_ts_ids: Dict[str, TimeseriesContainer],
        actual_ts_ids: Dict[str, TimeseriesContainer],
        attributes_to_ignore: List | None = None,
    ) -> None:
        """Compares two time series id metadata objects.

        Iterates through the dictionary of expected time series id metadata objects, comparing each key value pair
        to the actual data provided, raising an error if the comparison fails.

        If attributes_to_ignore is provided, any attributes named within the list will be ignored for the comparison.

        """
        for expected_ts_id, expected_ts_container in expected_ts_ids.items():
            # Extract the dictionary representation of the TimeseriesContainer object to make comparisons easier
            expected_ts_dict = expected_ts_container.__dict__

            actual_ts_container = actual_ts_ids.get(expected_ts_id)
            if not actual_ts_container:
                raise ComparisonError(f"The expected time series ID: `{expected_ts_id}` could not be found.")
            actual_ts_dict = actual_ts_container.__dict__

            for expected_key, expected_value in expected_ts_dict.items():
                actual_value = actual_ts_dict.get(expected_key)
                if actual_value is None and expected_value is not None:
                    raise ComparisonError(
                        f"The expected key `{expected_key}` could not be found for time series ID: `{expected_ts_id}`"
                    )

                # ts.TimeFrame objects require custom comparison to ensure all attributes are compared correctly.
                if isinstance(expected_value, ts.TimeFrame):
                    assert expected_value == actual_value
                    continue

                # Sort any lists to be compared to ensure the comparison is consistent
                if isinstance(expected_value, list):
                    for item in expected_value:
                        if item not in actual_value:
                            raise ComparisonError(
                                f"The expected and actual values for key `{expected_key}` (ts_id: {expected_ts_id}) "
                                f"do not match. Expected value: `{item} could not be found in: `{actual_value}`"
                            )
                    continue

                if expected_value != actual_value:
                    raise ComparisonError(
                        f"The expected and actual values for key `{expected_key}` (ts_id: {expected_ts_id}) do not "
                        f"match. Expected value: `{expected_value}. Actual value: `{actual_value}`"
                    )
