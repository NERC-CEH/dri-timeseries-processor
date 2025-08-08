import json
import os
import subprocess
import shutil
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List
from dritimeseriesprocessor.typing import TimeseriesContainerWithDerivations

import polars as pl
from polars.testing import assert_frame_equal
from time_stream import Period, TimeSeries


class ComparisonError(Exception):
    pass


def load_json(json_path: str) -> Dict[str, Any]:
    """
    Generic json reading function used for loading test data from file.

    Args:
        json_path: Path to read the json data from.

    Returns:
        Dictionary containing the json data read from file.

    """
    with open(json_path) as json_file:
        return json.load(json_file)


def df_to_ts(df: pl.DataFrame) -> "TimeSeries":
    """Convert a Polars DataFrame to a TimeSeries object."""

    # Add time column according to the length of the DataFrame
    time_name = "time"
    date_list = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(len(df))]
    df = df.with_columns(pl.Series(name="time", values=date_list))

    # Reorder columns to put "time" first
    df = df.select(["time"] + [col for col in df.columns if col != "time"])

    # Set resolution and periodicity
    resolution = Period.of_iso_duration("P1D")

    return TimeSeries(
        df=df,
        time_name=time_name,
        resolution=resolution,
        periodicity=resolution,
        metadata={},
    )


class TestHelper(unittest.TestCase):
    def setUp(self) -> None:
        """Sets up the testing environment.

        Creates a temp directory within the main test data folder to use as the current working directory for all tests
        The temp directory is deleted and recreated if it already exists.

        Identifies the data directory and stores it alongside a number of useful directories, such as the input and
        output subdirectories.

        """
        super().setUp()

        self.data_dir = Path(__file__).parents[1].joinpath("data")
        self.input_dir = self.data_dir.joinpath("inputs")
        self.output_dir = self.data_dir.joinpath("outputs")
        self.temp_dir = self.data_dir.joinpath("temp")

        self.original_cwd = os.getcwd()

        self.reset_temp_dir()

        # Set the current working directory to be the temp dir so that all test outputs are written there
        os.chdir(self.temp_dir)

        # Clear s3 bucket before test
        subprocess.run(["awslocal", "s3", "rm", "s3://ukceh-fdri-staging-timeseries-processed", "--recursive"])

    def tearDown(self) -> None:
        """Tears down the testing environment

        Resets the temporary directory, deleting and recreating it.
        Resets the current working directory back to it's original value.

        """
        super().tearDown()

        self.reset_temp_dir()

        # Reset the current working directory
        os.chdir(self.original_cwd)

        # Clear s3 bucket after test
        subprocess.run(["awslocal", "s3", "rm", "s3://ukceh-fdri-staging-timeseries-processed", "--recursive"])

    def reset_temp_dir(self) -> None:
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

        self.temp_dir.mkdir(parents=True, exist_ok=True)

    @property
    def metadata_api_data(self) -> Dict[str, Dict[str, Any]]:
        """Default metadata api data dictionary.

        Loads the metadata response json data for the following data:
            - list all available cosmos sites
            - ts id metadata for all variables for cosmos site ALIC1
            - ts definition metadata for all variables for cosmos site ALIC1

        Returns:
            Dictionary of metadata url: loaded json data for url

        """
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

    def load_ts_ids_from_json_file(self, json_path: str) -> Dict[str, TimeseriesContainerWithDerivations]:
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
    ) -> Dict[str, TimeseriesContainerWithDerivations]:
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
    def convert_ts_ids_to_dict(ts_ids: Dict[str, TimeseriesContainerWithDerivations]) -> Dict[str, Dict[str, Any]]:
        """
        Convert a dictionary of timeseries ids (containing TimeSeries data objects) into a dictionary that is easily
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
        expected_ts_ids: Dict[str, TimeseriesContainerWithDerivations],
        actual_ts_ids: Dict[str, TimeseriesContainerWithDerivations],
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
