import pytest
from tests.utils.fixture_helpers import discover_json_test_cases, load_json_file
from tests.utils.validation_helpers import invalid_raises, valid_parses

from dritimeseriesprocessor.models.api_models.dataset_observation import ObservationDatasetResponse


class TestObservationDataset:
    @pytest.mark.parametrize(
        "filename",
        discover_json_test_cases("api_json/valid/dataset_observation"),
    )
    def test_valid_dataset(self, filename: str) -> None:
        valid_parses(load_json_file, filename, ObservationDatasetResponse)

    @pytest.mark.parametrize(
        "filename",
        discover_json_test_cases("api_json/invalid/generic")
        + discover_json_test_cases("api_json/invalid/dataset_observation"),
    )
    def test_invalid_dataset(self, filename: str) -> None:
        invalid_raises(load_json_file, filename, ObservationDatasetResponse)
