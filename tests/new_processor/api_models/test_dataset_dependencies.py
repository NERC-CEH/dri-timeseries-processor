import pytest
from new_processor.api_models.dataset_dependencies import DatasetDependencies
from tests.utils.fixture_helpers import discover_json_test_cases, load_json_file
from tests.utils.validation_helpers import invalid_raises, valid_parses


class TestDatasetDependencies:
    @pytest.mark.parametrize("filename", discover_json_test_cases("api_json/valid/dataset_dependencies"))
    def test_valid_dataset(self, filename: str) -> None:
        valid_parses(load_json_file, filename, DatasetDependencies)

    @pytest.mark.parametrize(
        "filename",
        discover_json_test_cases("api_json/invalid/generic")
        + discover_json_test_cases("api_json/invalid/dataset_dependencies"),
    )
    def test_invalid_dataset(self, filename: str) -> None:
        invalid_raises(load_json_file, filename, DatasetDependencies)
