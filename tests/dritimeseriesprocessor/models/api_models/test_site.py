import pytest
from tests.utils.fixture_helpers import discover_json_test_cases, load_json_file
from tests.utils.validation_helpers import invalid_raises, valid_parses

from dritimeseriesprocessor.models.api_models.site import SiteResponse


class TestSite:
    @pytest.mark.parametrize("filename", discover_json_test_cases("api_json/valid/site"))
    def test_valid_site(self, filename: str) -> None:
        valid_parses(load_json_file, filename, SiteResponse)

    @pytest.mark.parametrize(
        "filename",
        discover_json_test_cases("api_json/invalid/generic") + discover_json_test_cases("api_json/invalid/site"),
    )
    def test_invalid_site(self, filename: str) -> None:
        invalid_raises(load_json_file, filename, SiteResponse)
