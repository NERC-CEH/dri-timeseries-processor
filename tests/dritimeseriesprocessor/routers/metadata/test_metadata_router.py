from unittest.mock import MagicMock

import pytest
from driutils.metadata_api.models.site import SiteResponse

from dritimeseriesprocessor.models.api_models.dataset_timeseries import TimeSeriesDatasetResponse
from dritimeseriesprocessor.routers.metadata.metadata_router import MetadataRouter
from dritimeseriesprocessor.utils.urls import CONFIGURATION_TYPE_URI


@pytest.fixture
def mock_api_manager() -> MagicMock:
    """Mock out MetadataAPIManager so no backend is needed."""
    api_manager = MagicMock()
    return api_manager


@pytest.fixture
def minimal_dataset_response() -> dict:
    """Minimal valid dataset response for testing."""
    return {
        "meta": {
            "@id": "test-meta",
            "publisher": "test",
            "license": "test-license",
            "licenseName": "Test License",
            "comment": "test comment",
            "version": "1.0",
            "hasFormat": ["json"],
        },
        "items": [],
    }


@pytest.fixture
def minimal_site_response() -> dict:
    """Minimal valid site response for testing."""
    return {
        "meta": {
            "@id": "test-meta",
            "publisher": "test",
            "license": "test-license",
            "licenseName": "Test License",
            "comment": "test comment",
            "version": "1.0",
            "hasFormat": ["json"],
        },
        "items": [{"@id": "http://example.com/site/test-site", "identifier": ["TEST"], "label": ["Test Site"]}],
    }


@pytest.fixture
def minimal_config_response() -> dict:
    """Minimal valid config response for testing."""
    return {
        "meta": {
            "@id": "test-meta",
            "publisher": "test",
            "license": "test-license",
            "licenseName": "Test License",
            "comment": "test comment",
            "version": "1.0",
            "hasFormat": ["json"],
        },
        "items": [],
    }


def create_metadata_router(
    mock_api_manager: MagicMock, response: dict, monkeypatch: pytest.MonkeyPatch
) -> MetadataRouter:
    """Create a MetadataRouter with mocked API manager."""
    mock_api_manager.make_paginated_api_call.return_value = response
    monkeypatch.setattr("dritimeseriesprocessor.routers.metadata.metadata_router.MetadataAPIManager", mock_api_manager)
    router = MetadataRouter("example_host")
    router.api_manager = mock_api_manager
    return router


class TestFetchDatasetByParams:
    def test_constructs_correct_url(
        self, mock_api_manager: MagicMock, minimal_dataset_response: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        router = create_metadata_router(mock_api_manager, minimal_dataset_response, monkeypatch)

        query_params = (("site", "test-site"), ("variable", "temperature"))
        router.fetch_dataset_by_params(query_params)

        expected_url = "example_host/id/dataset"
        mock_api_manager.make_paginated_api_call.assert_called_once_with(expected_url, query_params)

    def test_return_object(
        self, mock_api_manager: MagicMock, minimal_dataset_response: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that the response is parsed as TimeSeriesDatasetResponse."""
        router = create_metadata_router(mock_api_manager, minimal_dataset_response, monkeypatch)
        result = router.fetch_dataset_by_params(tuple())
        assert isinstance(result, TimeSeriesDatasetResponse)


class TestFetchDatasetById:
    def test_constructs_correct_url(
        self, mock_api_manager: MagicMock, minimal_dataset_response: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        router = create_metadata_router(mock_api_manager, minimal_dataset_response, monkeypatch)
        router.fetch_dataset_by_id("test-id")

        expected_url = "example_host/id/dataset/test-id?_view=timeseries"
        mock_api_manager.make_paginated_api_call.assert_called_once_with(expected_url)

    def test_return_object(
        self, mock_api_manager: MagicMock, minimal_dataset_response: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that the response is parsed as TimeSeriesDatasetResponse."""
        router = create_metadata_router(mock_api_manager, minimal_dataset_response, monkeypatch)
        result = router.fetch_dataset_by_id("test-id")
        assert isinstance(result, TimeSeriesDatasetResponse)


class TestFetchAllDependencies:
    def test_constructs_correct_url(
        self, mock_api_manager: MagicMock, minimal_dataset_response: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        router = create_metadata_router(mock_api_manager, minimal_dataset_response, monkeypatch)
        router.fetch_all_dependencies("test-id")

        expected_url = "example_host/id/dataset/test-id/_all_dependencies"
        mock_api_manager.make_paginated_api_call.assert_called_once_with(expected_url)

    def test_return_object(
        self, mock_api_manager: MagicMock, minimal_dataset_response: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that the response is parsed as TimeSeriesDatasetResponse."""
        router = create_metadata_router(mock_api_manager, minimal_dataset_response, monkeypatch)
        result = router.fetch_all_dependencies("test-id")
        assert isinstance(result, TimeSeriesDatasetResponse)


class TestFetchProcessingConfigs:
    @pytest.mark.parametrize(
        "num_ids, batch_size, expected_calls",
        [
            (10, 5, 2),
            (10, 10, 1),
            (10, 3, 4),
            (1000, 50, 20),
        ],
    )
    def test_batches(
        self,
        num_ids: int,
        batch_size: int,
        expected_calls: int,
        mock_api_manager: MagicMock,
        minimal_config_response: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        router = create_metadata_router(mock_api_manager, minimal_config_response, monkeypatch)
        dataset_ids = [str(n) for n in range(num_ids)]
        router.fetch_processing_configs(dataset_ids, batch_size=batch_size)
        assert mock_api_manager.make_paginated_api_call.call_count == expected_calls

    def test_constructs_correct_url(
        self, mock_api_manager: MagicMock, minimal_config_response: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        router = create_metadata_router(mock_api_manager, minimal_config_response, monkeypatch)
        dataset_ids = ["a", "b", "c"]
        router.fetch_processing_configs(dataset_ids)

        expected_url = "example_host/id/data-processing-configuration"
        config_type_params = [
            ("type", f"{CONFIGURATION_TYPE_URI}/correction-configuration"),
            ("type", f"{CONFIGURATION_TYPE_URI}/infill-configuration"),
            ("type", f"{CONFIGURATION_TYPE_URI}/qc"),
        ]
        dataset_params = [("appliesToTimeSeries", dataset_id) for dataset_id in dataset_ids]
        mock_api_manager.make_paginated_api_call.assert_called_once_with(
            expected_url, tuple(config_type_params + dataset_params)
        )


class TestFetchSites:
    def test_constructs_correct_url(
        self, mock_api_manager: MagicMock, minimal_site_response: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        router = create_metadata_router(mock_api_manager, minimal_site_response, monkeypatch)
        router.fetch_sites(["test-site"])

        expected_url = "example_host/id/site?_view=annotated"
        params = (("@id", "test-site"),)
        mock_api_manager.make_paginated_api_call.assert_called_once_with(expected_url, params)

    def test_return_object(
        self, mock_api_manager: MagicMock, minimal_site_response: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that the response is parsed as DataProcessingConfiguration."""
        router = create_metadata_router(mock_api_manager, minimal_site_response, monkeypatch)
        result = router.fetch_sites(["test-site"])
        assert isinstance(result, SiteResponse)
