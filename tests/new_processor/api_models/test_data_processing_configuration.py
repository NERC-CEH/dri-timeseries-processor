from typing import Callable

import pytest
from src.new_processor.api_models.data_processing_configuration import DataProcessingConfiguration
from tests.utils.fixture_helpers import discover_json_test_cases
from tests.utils.validation_helpers import invalid_raises, valid_parses


class TestDatasetDependencies:
    @pytest.mark.parametrize("filename", discover_json_test_cases("api_json/valid/data_processing_configuration"))
    def test_valid_dataset(self, load_json_file: Callable, filename: str) -> None:
        valid_parses(load_json_file, filename, DataProcessingConfiguration)

    @pytest.mark.parametrize(
        "filename",
        discover_json_test_cases("api_json/invalid/generic")
        + discover_json_test_cases("api_json/invalid/data_processing_configuration"),
    )
    def test_invalid_dataset(self, load_json_file: Callable, filename: str) -> None:
        invalid_raises(load_json_file, filename, DataProcessingConfiguration)
