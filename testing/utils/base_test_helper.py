import json
import os
import shutil
import unittest
from pathlib import Path
from typing import Any, Dict


class ComparisonError(Exception):
    pass




class BaseTestHelper(unittest.TestCase):
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

    def tearDown(self) -> None:
        """Tears down the testing environment

        Resets the temporary directory, deleting and recreating it.
        Resets the current working directory back to it's original value.

        """
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
        """Default metadata api data dictionary.

        Loads the metadata response json data for the following data:
            - list all available cosmos sites
            - ts id metadata for all variables for cosmos site ALIC1
            - ts definition metadata for all variables for cosmos site ALIC1

        Returns:
            Dictionary of metadata url: loaded json data for url

        """
        return {
            "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/network/cosmos": self.load_json(
                self.input_dir.joinpath("mock_metadata_api", "sites_metadata.json")
            ),
            "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset": self.load_json(
                self.input_dir.joinpath("mock_metadata_api", "ts_id_metadata_alic1.json")
            ),
            "https://dri-metadata-api.staging.eds.ceh.ac.uk/ref/time-series-definition": self.load_json(
                self.input_dir.joinpath("mock_metadata_api", "ts_def_metadata.json")
            ),
        }

    def create_ts_dependency_api_data(self) -> Dict[str, Any]:
        base_url = "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/cosmos-alic1-"
        ts_dependencies_dir = self.input_dir.joinpath("mock_metadata_api", "ts_dependencies_alic1")

        dependency_suffixes = [
            "pe_30min_processed",
            "rn_30min_processed",
            "swin_30min_processed",
            "lwout_30min_processed",
            "swout_30min_processed",
            "lwin_30min_processed",
            "pa_30min_processed",
            "g1_30min_processed",
            "g2_30min_processed",
            "rh_30min_processed",
            "ws_30min_processed",
            "ta_30min_processed",
            "tnr01c_30min_processed",
            "tnr01c_30min_raw",
            "battv_30min_raw",
            "scans_30min_raw",
            "swin_30min_raw",
            "lwout_30min_raw",
            "swout_30min_raw",
            "lwin_30min_raw",
            "pa_30min_raw",
            "g2_30min_raw",
            "rh_30min_raw",
            "ws_30min_raw",
            "ta_30min_raw",
            "g1_30min_raw",
        ]

        api_data = {}
        for dependency_suffix in dependency_suffixes:
            api_data[f"{base_url}{dependency_suffix}/_dependencies"] = self.load_json(
                ts_dependencies_dir.joinpath(f"{dependency_suffix}.json")
            )

        return api_data

    @staticmethod
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
