import pytest
from src.new_processor.api_models.dataset_timeseries import TimeSeriesDataset
from tests.utils.fixture_helpers import discover_json_test_cases, load_json_file
from tests.utils.validation_helpers import invalid_raises, valid_parses


class TestTimeSeriesDataset:
    @pytest.mark.parametrize("filename", discover_json_test_cases("api_json/valid/dataset_timeseries"))
    def test_valid_dataset(self, filename: str) -> None:
        valid_parses(load_json_file, filename, TimeSeriesDataset)

    @pytest.mark.parametrize(
        "filename",
        discover_json_test_cases("api_json/invalid/generic")
        + discover_json_test_cases("api_json/invalid/dataset_timeseries"),
    )
    def test_invalid_dataset(self, filename: str) -> None:
        invalid_raises(load_json_file, filename, TimeSeriesDataset)
