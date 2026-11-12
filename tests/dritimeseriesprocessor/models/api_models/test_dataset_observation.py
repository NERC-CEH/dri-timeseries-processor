import pytest
from tests.utils.fixture_helpers import TEST_DATA_INPUT_DIR, discover_json_test_cases, load_json_file
from tests.utils.validation_helpers import invalid_raises, valid_parses

from dritimeseriesprocessor.models.api_models.dataset_observation import (
    ObservationDatasetItem,
    ObservationDatasetResponse,
)


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


class TestDistributionUrl:
    @pytest.fixture
    def dataset(self) -> ObservationDatasetItem:
        """A dataset whose metadata access URL ends in a slash."""
        data = load_json_file(TEST_DATA_INPUT_DIR / "api_json/valid/dataset_observation/flux_plynl_processed.json")
        return ObservationDatasetResponse.model_validate(data).items[0]

    def test_trailing_slash_is_removed(self, dataset: ObservationDatasetItem) -> None:
        """Tests that the first access URL is returned without its trailing slash."""
        expected = "s3://ukceh-dri-staging-processed/network=FDRI/collection=PROCESSED_FLUX/site=flux-plynl"
        assert dataset.distribution_url == expected

    def test_none_when_no_distribution(self, dataset: ObservationDatasetItem) -> None:
        """Tests that a dataset with no distribution has no access URL."""
        assert dataset.model_copy(update={"distribution": None}).distribution_url is None

    def test_none_when_distribution_has_no_access_url(self, dataset: ObservationDatasetItem) -> None:
        """Tests that a distribution with no access URL gives no access URL."""
        assert dataset.distribution is not None
        distribution = dataset.distribution[0].model_copy(update={"access_url": None})

        assert dataset.model_copy(update={"distribution": [distribution]}).distribution_url is None
