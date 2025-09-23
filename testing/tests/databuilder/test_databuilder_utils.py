import os
from pathlib import Path
from unittest import mock

import pytest

from databuilder import utils
from testing.utils.base_test_helper import BaseTestHelper


@pytest.fixture
def cosmos_data() -> Path:
    data_dir = Path(__file__).parents[3] / "parquet-data"
    cosmos_data = data_dir / "cosmos"

    return cosmos_data


class TestInitialization:
    def test_creation_from_nonexistance(self, base_test_helper: BaseTestHelper) -> None:
        output = base_test_helper.temp_dir.joinpath("out-data")

        assert not output.exists()

        utils._create_directory(output, purge=False)

        assert output.exists()

    def test_creation_of_existing_dir_no_purge(self, base_test_helper: BaseTestHelper) -> None:
        output = base_test_helper.temp_dir.joinpath("out-data")
        os.makedirs(output)
        test_file = output / "test.txt"

        with open(test_file, "w") as f:
            f.write("test text")

        assert test_file.exists()

        expected_content = os.listdir(output)

        utils._create_directory(output, purge=False)

        assert expected_content, os.listdir(output)

    def test_creation_of_existing_dir_with_purge(self, base_test_helper: BaseTestHelper) -> None:
        output = base_test_helper.temp_dir.joinpath("out-data")
        os.makedirs(output)
        test_file = output / "test.txt"

        with open(test_file, "w") as f:
            f.write("test text")

        assert os.listdir(output) == [test_file.parts[-1]]

        utils._create_directory(output, purge=True)

        assert os.listdir(output) == []

    def test_data_copied_to_directory(self, base_test_helper: BaseTestHelper, cosmos_data: str) -> None:
        output = base_test_helper.temp_dir.joinpath("out-data")
        utils._create_directory(output)

        utils._copy_files(output, src=cosmos_data)

        assert os.listdir(output) == os.listdir(cosmos_data)

    def test_data_copied_to_directory_default_value(self, base_test_helper: BaseTestHelper, cosmos_data: str) -> None:
        output = base_test_helper.temp_dir.joinpath("out-data")
        utils._create_directory(output)

        utils._copy_files(output)

        assert os.listdir(output) == os.listdir(cosmos_data)

    @mock.patch("databuilder.utils._create_directory")
    @mock.patch("databuilder.utils._copy_files")
    def test_init_helper_method(
        self, mock_copy_files: mock.MagicMock, mock_create_directory: mock.MagicMock, base_test_helper: BaseTestHelper
    ) -> None:
        """Tests that the helper method executes the expected private methods"""
        output = base_test_helper.temp_dir.joinpath("out-data")

        utils.initialise_directory(output)

        mock_copy_files.assert_called_once()
        mock_create_directory.assert_called_once()
