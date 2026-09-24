from unittest.mock import MagicMock, patch

import pytest
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.derivation.derivation_methods import DerivationMethod
from dritimeseriesprocessor.operations.derivation.derivation_pipeline import DerivationPipeline
from dritimeseriesprocessor.operations.operation_pipeline import OperationPipeline
from utils.data_creation import create_timeframe


@pytest.fixture
def site_metadata() -> SiteMetadata:
    """Create site metadata for the pipeline to pass on to its methods."""
    return SiteMetadata(site_id="site-1", network="cosmos", lat=54.0, altitude=74.0)


@pytest.fixture
def mock_container() -> MagicMock:
    """Create a mock container describing the dataset being derived."""
    container = MagicMock(spec=TimeSeriesContainer)
    container.source_column = "vwc"
    container.resolution = "PT1H"
    container.periodicity = "PT1H"
    container.time_anchor = "start"
    return container


class TestRun:
    def test_container_context_is_added_to_every_method_config(
        self, site_metadata: SiteMetadata, mock_container: MagicMock
    ) -> None:
        """Tests that each method config is given the site metadata and the output dataset's time properties."""
        method_config = DataProcessingMethodConfig(method="test", params={})
        config = MagicMock(spec=DataProcessingConfig)
        config.method_configs = [method_config]

        pipeline = DerivationPipeline(site_metadata, {})
        with patch.object(OperationPipeline, "run") as mock_run:
            pipeline.run(mock_container, {}, config)

        assert method_config.params["site_metadata"] is site_metadata
        assert method_config.params["container"] is mock_container
        assert method_config.params["output_col"] == "vwc"
        assert method_config.params["resolution"] == "PT1H"
        assert method_config.params["periodicity"] == "PT1H"
        assert method_config.params["time_anchor"] == "start"
        mock_run.assert_called_once()


class TestApply:
    def test_dependencies_are_injected_before_the_method_runs(self, site_metadata: SiteMetadata) -> None:
        """Tests that a dependency's data is put into the params under its own column name before dispatch."""
        dependency = MagicMock(spec=TimeSeriesContainer)
        dependency.source_column = "TA"
        dependency.data = create_timeframe([1.0, 2.0], "TA")
        config = DataProcessingMethodConfig(method="test", params={"dep_ts": "ts_1"})

        pipeline = DerivationPipeline(site_metadata, {})
        with patch.object(DerivationMethod, "get") as mock_get:
            pipeline.apply(None, config, {"ts_1": dependency})

        assert config.params["ta"] is dependency.data
        assert config.params["dataset_repository"] == {"ts_1": dependency}
        mock_get.assert_called_once_with("test")

    def test_method_is_run_with_the_timeframe_it_was_given(self, site_metadata: SiteMetadata) -> None:
        """Tests that the TimeFrame is handed to the method, which ignores it as derivation builds its own."""
        config = DataProcessingMethodConfig(method="test", params={})
        expected = create_timeframe([1.0, 2.0])

        pipeline = DerivationPipeline(site_metadata, {})
        with patch.object(DerivationMethod, "get") as mock_get:
            mock_get.return_value.run.return_value = expected
            result = pipeline.apply(None, config, {})

        mock_get.return_value.run.assert_called_once_with(config)
        assert result is expected


class TestFlags:
    def test_derivation_has_no_flag_column_of_its_own(self, site_metadata: SiteMetadata) -> None:
        """Tests that no operation-specific flag column is requested, unlike QC or corrections."""
        assert DerivationPipeline(site_metadata, {}).get_flag_column("vwc") is None

    def test_flag_mask_is_not_supported(self, site_metadata: SiteMetadata) -> None:
        """Tests that asking for a flag mask fails, as derivation does not flag its own results."""
        pipeline = DerivationPipeline(site_metadata, {})
        with pytest.raises(NotImplementedError):
            pipeline.compute_flag_mask(MagicMock(spec=ts.TimeFrame), MagicMock(spec=ts.TimeFrame), "vwc")

    def test_rows_without_a_derived_value_get_the_missing_core_flag(self, site_metadata: SiteMetadata) -> None:
        """Tests that the 'missing' core flag is stamped on the rows where the derivation produced no value."""
        tf = create_timeframe([1.0, None, 3.0], "vwc")
        tf.register_flag_system("core", {"missing": 4})
        tf.init_flag_column("core", "vwc_CORE_FLAG")

        result = DerivationPipeline(site_metadata, {}).core_flag_updater(tf)

        assert result.df["vwc_CORE_FLAG"].to_list() == [0, 4, 0]

    def test_missing_flag_is_skipped_when_there_is_no_core_flag_column(self, site_metadata: SiteMetadata) -> None:
        """Tests that a dataset without a core flag column passes through untouched."""
        tf = create_timeframe([1.0, None, 3.0], "vwc")

        result = DerivationPipeline(site_metadata, {}).core_flag_updater(tf)

        assert result.df.columns == ["time", "vwc"]
        assert result.df["vwc"].to_list() == [1.0, None, 3.0]
