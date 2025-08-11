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
    def default_metadata_api_data(self) -> Dict[str, Dict[str, Any]]:
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
                self.input_dir.joinpath("mock_metadata_api", "ts_id_metadata_alic1_bunny.json")
            ),
            "https://dri-metadata-api.staging.eds.ceh.ac.uk/ref/time-series-definition": self.load_json(
                self.input_dir.joinpath("mock_metadata_api", "ts_def_metadata.json")
            ),
        }

    def create_all_metadata_api_data(self) -> Dict[str, Any]:
        """
        Construct a dictionary containing all metadata api data, adding ts_dependency, corrections and infill
        configuration api responses to the default api response data.
        """
        return (
            self.default_metadata_api_data
            | self.create_ts_dependency_api_data()
            | self.create_corrections_api_data()
            | self.create_infill_configurations_api_data()
            | self.create_qc_configurations_api_data()
        )

    def create_ts_dependency_api_data(self) -> Dict[str, Any]:
        """Construct the timeseries dependency api data response."""
        base_url = "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/cosmos"
        base_dir = self.input_dir.joinpath("mock_metadata_api", "ts_dependencies")
        base_url = "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/cosmos-"

        return self._load_api_data_from_file(base_url, base_dir, url_suffix="/_dependencies")

    def create_corrections_api_data(self) -> Dict[str, Any]:
        """Construct the corrections metadata api data response."""
        base_url = (
            "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/data-processing-configuration.json?type=http://fdri."
            "ceh.ac.uk/ref/common/configuration-type/correction-configuration&appliesToTimeSeries=http://fdri.ceh.ac."
            "uk/id/dataset/cosmos-"
        )
        corrections_dir = self.input_dir.joinpath("mock_metadata_api", "correction_configurations")

        return self._load_api_data_from_file(base_url, corrections_dir)

    def create_infill_configurations_api_data(self) -> Dict[str, Any]:
        """Construct the infill configurations api data response."""
        base_url = (
            "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/data-processing-configuration.json?type=http://fdri."
            "ceh.ac.uk/ref/common/configuration-type/infill-configuration&appliesToTimeSeries=http://fdri.ceh.ac.uk/"
            "id/dataset/cosmos-"
        )
        base_dir = self.input_dir.joinpath("mock_metadata_api", "infill_configurations")

        return self._load_api_data_from_file(base_url, base_dir)

    def create_qc_configurations_api_data(self) -> Dict[str, Any]:
        """Construct the qc configurations api data response."""
        base_url = (
            "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/data-processing-configuration.json?type=http://fdri."
            "ceh.ac.uk/ref/common/configuration-type/qc&appliesToTimeSeries=http://fdri.ceh.ac.uk/id/dataset/cosmos-"
        )

        base_dir = self.input_dir.joinpath("mock_metadata_api", "qc_configurations")

        return self._load_api_data_from_file(base_url, base_dir)

    def _load_api_data_from_file(self, base_url: str, base_dir: Path, url_suffix: str = None) -> Dict[str, Any]:
        """
        Using the provided base directory, read every json file contained within it, using the filename to construct the
        url to index the json data against in the output api data dictionary.

        Args:
            base_url: Base url to add the json filename to. The complete url should match the corresponding url that
                would be used to query the same data against the Metadat API.
            base_dir: Path to the directory containing all the json files to be read.
            url_suffix: Any suffix to add to the

        Returns:
            Dictionary containing the api response data indexed by url.

        """
        if url_suffix is None:
            url_suffix = ""

        # The name of the json file should be based on the remaining section of the base url, e.g. tnr01c_30min_raw.json
        api_data = {}
        for json_path in base_dir.glob("*.json"):
            url = f"{base_url}{json_path.stem}{url_suffix}"
            with open(json_path) as json_file:
                try:
                    json_data = json.load(json_file)
                except:
                    print()
            api_data[url] = json_data

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
