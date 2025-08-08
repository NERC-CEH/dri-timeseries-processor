import json
import os
import shutil
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Union

import polars as pl
from polars.testing import assert_frame_equal
from time_stream import Period, TimeSeries

from testing.utils.base_test_helper import BaseTestHelper, ComparisonError


class TimeSeriesTestHelper(BaseTestHelper):
    def load_ts_ids_from_json_file(self, json_path: str) -> Dict[str, Dict[str, Union[str, TimeSeries]]]:
        """
        Loads time series id metadata (to be converted to a TimeSeriesContainer object) from a json file, iterating
        over each item to create the relevant TimeSeries objects for any items which contain data attributes.

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
    ) -> Dict[str, Dict[str, Union[str, TimeSeries]]]:
        """
        Loads time series id metadata (to be converted to a TimeSeriesContainer object) from a dictionary, iterating
        over each item to create the relevant TimeSeries objects for any items which contain data attributes.

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
        """
        Convert a dictionary of timeseries ids (containing TimeSeries data objects) into a dictionary that is easily
        written to a json file.

        Args:
            ts_ids (Dict[str, Dict[str, Union[str, TimeSeries]]]): Dictionary of time series id metadata.

        Returns:
            Reformatted dictionary of timeseries id metadata.

        """
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
        attributes_to_ignore: List | None = None,
    ) -> None:
        """Compares two time series id metadata objects.

        Iterates through the dictionary of expected time series id metadata objects, comparing each key value pair
        to the actual data provided, raising an error if the comparison fails.

        If attributes_to_ignore is provided, any attributes named within the list will be ignored for the comparison.

        """
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
                    self.compare_timeseries_objects(
                        expected_timeseries=expected_value,
                        actual_timeseries=actual_value,
                        attributes_to_ignore=attributes_to_ignore,
                    )
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
    def compare_timeseries_objects(
        expected_timeseries: TimeSeries, actual_timeseries: TimeSeries, attributes_to_ignore: List | None = None
    ) -> None:
        """Compares two TimeSeries objects

        Iterates through the available TimeSeries attributes comparing the values from the expected and actual
        TimeSeries objects for each, raising an error if they don't match.

        """
        if attributes_to_ignore is None:
            attributes_to_ignore = []

        # Check the polars dataframes match. Due to the way expected data may have been stored in json ignore the
        # data types to avoid failures caused by data being loaded as Int64 instead of UInt32 for example.
        assert_frame_equal(expected_timeseries.df, actual_timeseries.df, check_dtype=False)

        timeseries_attributes = [
            "time_name",
            "resolution",
            "periodicity",
            "supplementary_columns",
            "flag_systems",
            "flag_columns",
            "metadata",
        ]
        for attribute_name in timeseries_attributes:
            # Skip any attributes which have been requested to ignore.
            if attribute_name in attributes_to_ignore:
                continue

            expected_value = getattr(expected_timeseries, attribute_name)
            actual_value = getattr(actual_timeseries, attribute_name)

            # metadata and column_metadata are stored as functions which need to be called to extract their values
            # before they can be compared.
            if callable(expected_value):
                expected_value = expected_value()
                actual_value = actual_value()

            if expected_value != actual_value:
                raise ComparisonError(
                    f"The expected TimeSeries attribute value for `{attribute_name}` does not match. "
                    f"Expected value: `{expected_value}. Actual value: `{actual_value}`"
                )
