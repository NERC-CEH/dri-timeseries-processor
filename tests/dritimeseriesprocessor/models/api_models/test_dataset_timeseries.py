import pytest
from tests.utils.fixture_helpers import discover_json_test_cases, load_json_file
from tests.utils.validation_helpers import invalid_raises, valid_parses

from dritimeseriesprocessor.models.api_models.dataset_timeseries import TimeSeriesDatasetResponse


class TestTimeSeriesDataset:
    @pytest.mark.parametrize(
        "filename",
        discover_json_test_cases("api_json/valid/dataset_timeseries")
        + discover_json_test_cases("api_json/valid/dataset_dependencies"),
    )
    def test_valid_dataset(self, filename: str) -> None:
        valid_parses(load_json_file, filename, TimeSeriesDatasetResponse)

    @pytest.mark.parametrize(
        "filename",
        discover_json_test_cases("api_json/invalid/generic")
        + discover_json_test_cases("api_json/invalid/dataset_timeseries")
        + discover_json_test_cases("api_json/invalid/dataset_dependencies"),
    )
    def test_invalid_dataset(self, filename: str) -> None:
        invalid_raises(load_json_file, filename, TimeSeriesDatasetResponse)
