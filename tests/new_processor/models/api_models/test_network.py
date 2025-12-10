import pytest
from tests.utils.fixture_helpers import discover_json_test_cases, load_json_file
from tests.utils.validation_helpers import invalid_raises, valid_parses

from new_processor.models.api_models.network import Network


class TestNetwork:
    @pytest.mark.parametrize("filename", discover_json_test_cases("api_json/valid/network"))
    def test_valid_dataset(self, filename: str) -> None:
        valid_parses(load_json_file, filename, Network)

    @pytest.mark.parametrize(
        "filename",
        discover_json_test_cases("api_json/invalid/generic") + discover_json_test_cases("api_json/invalid/network"),
    )
    def test_invalid_dataset(self, filename: str) -> None:
        invalid_raises(load_json_file, filename, Network)
