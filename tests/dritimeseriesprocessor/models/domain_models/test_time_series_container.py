from datetime import datetime, timedelta

import polars as pl
import pytest
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.time_series_container import (
    check_common_attributes,
    group_containers,
)
from dritimeseriesprocessor.utils.enums import ConfigurationType, DatasetType, ProcessingLevel
from utils.data_creation import make_time_series_container


def make_daily_df(n_rows: int = 3, col_name: str = "value") -> pl.DataFrame:
    dates = [datetime(2025, 1, 1) + timedelta(days=i) for i in range(n_rows)]
    return pl.DataFrame({"time": dates, col_name: list(range(n_rows))})


class TestS3Bucket:
    def test_parses_bucket_from_distribution_url(self) -> None:
        c = make_time_series_container("a")
        c.dataset_type = DatasetType.OBSERVATION_DATASET
        c.distribution_url = "s3://my-bucket/some/path/"
        assert c.s3_bucket == "my-bucket"

    def test_falls_back_to_source_bucket_for_timeseries(self) -> None:
        c = make_time_series_container("a")
        c.dataset_type = DatasetType.TIMESERIES_DATASET
        c.distribution_url = "s3://ignored-bucket/path/"
        assert c.s3_bucket == c.source_bucket

    def test_falls_back_to_source_bucket_when_no_distribution_url(self) -> None:
        c = make_time_series_container("a")
        c.dataset_type = DatasetType.OBSERVATION_DATASET
        c.distribution_url = None
        assert c.s3_bucket == c.source_bucket


class TestS3DatasetPath:
    def test_parses_path_from_distribution_url(self) -> None:
        c = make_time_series_container("a")
        c.dataset_type = DatasetType.OBSERVATION_DATASET
        c.distribution_url = "s3://my-bucket/Flux/"
        assert c.s3_dataset_path == "Flux"

    def test_strips_trailing_slash(self) -> None:
        c = make_time_series_container("a")
        c.dataset_type = DatasetType.OBSERVATION_DATASET
        c.distribution_url = "s3://my-bucket/deep/nested/path/"
        assert c.s3_dataset_path == "deep/nested/path"

    def test_falls_back_to_source_dataset_for_timeseries(self) -> None:
        c = make_time_series_container("a")
        c.dataset_type = DatasetType.TIMESERIES_DATASET
        c.distribution_url = "s3://ignored/path/"
        assert c.s3_dataset_path == c.source_dataset

    def test_falls_back_to_source_dataset_when_no_distribution_url(self) -> None:
        c = make_time_series_container("a")
        c.dataset_type = DatasetType.OBSERVATION_DATASET
        c.distribution_url = None
        assert c.s3_dataset_path == c.source_dataset


class TestCheckCommonAttributes:
    def test_empty_containers_raises(self) -> None:
        """Tests that passing an empty container list raises a ValueError."""
        with pytest.raises(ValueError):
            check_common_attributes([], "a")
        with pytest.raises(ValueError):
            check_common_attributes([], ["a", "b"])

    containers = [
        make_time_series_container("a"),
        make_time_series_container("b"),
        make_time_series_container("c"),
    ]

    def test_single_attr(self) -> None:
        assert check_common_attributes(self.containers, "time_column_name") == "time"

    def test_multiple_attr(self) -> None:
        assert check_common_attributes(self.containers, ["time_column_name", "resolution", "processing_level"]) == [
            "time",
            "P1D",
            ProcessingLevel.PROCESSED,
        ]

    def test_single_attr_not_common(self) -> None:
        with pytest.raises(ValueError):
            check_common_attributes(self.containers, "ts_id")

    def test_multiple_attr_one_not_common(self) -> None:
        with pytest.raises(ValueError):
            check_common_attributes(self.containers, ["time_column_name", "resolution", "processing_level", "ts_id"])

    def test_multiple_attr_all_not_common(self) -> None:
        with pytest.raises(ValueError):
            check_common_attributes(self.containers, ["ts_id", "source_site", "source_column"])


class TestGroupContainers:
    def test_empty_containers_returns_empty_dict(self) -> None:
        assert group_containers((), ["network"]) == {}

    def test_single_attribute_all_same(self) -> None:
        a = make_time_series_container("a")
        b = make_time_series_container("b")
        c = make_time_series_container("c")
        # All containers share the same network value
        result = group_containers((a, b, c), ["network"])
        assert result == {("network",): [a, b, c]}

    def test_single_attribute_all_different(self) -> None:
        a = make_time_series_container("a")
        b = make_time_series_container("b")
        c = make_time_series_container("c")
        # ts_id is unique per container
        result = group_containers((a, b, c), ["ts_id"])
        assert result == {("a",): [a], ("b",): [b], ("c",): [c]}

    def test_multiple_attributes_composite_key(self) -> None:
        a = make_time_series_container("a")
        b = make_time_series_container("b")
        # Both share network and resolution - one group
        result = group_containers((a, b), ["network", "resolution"])
        assert result == {("network", "P1D"): [a, b]}

    def test_mixed_grouping(self) -> None:
        a1 = make_time_series_container("a")
        a2 = make_time_series_container("a")
        b = make_time_series_container("b")
        # Two containers share ts_id "a", one has ts_id "b"
        result = group_containers((a1, a2, b), ["ts_id"])
        assert result == {("a",): [a1, a2], ("b",): [b]}


class TestTimeColumnName:
    def test_time_column_name_can_be_none(self) -> None:
        container = make_time_series_container("a")
        container.time_column_name = None

        assert container.time_column_name is None

    def test_init_timeframe_skips_when_df_empty_and_time_column_name_is_none(self) -> None:
        container = make_time_series_container("a")
        container.time_column_name = None

        container.init_timeframe(pl.DataFrame({"time": [], "value": []}).cast({"time": pl.Datetime}))

        assert container.data is None


class TestInitTimeframe:
    def test_empty_df_leaves_data_none(self) -> None:
        container = make_time_series_container("a")
        container.init_timeframe(pl.DataFrame({"time": [], "value": []}).cast({"time": pl.Datetime}))
        assert container.data is None

    def test_non_empty_df_sets_data_as_timeframe(self) -> None:
        container = make_time_series_container("a")
        container.init_timeframe(make_daily_df())
        assert isinstance(container.data, ts.TimeFrame)

    def test_timeframe_metadata_contains_source_column(self) -> None:
        container = make_time_series_container("a")
        container.init_timeframe(make_daily_df())
        assert container.data.metadata == {"column_name": container.source_column}  # type: ignore[union-attr]

    def test_timeframe_uses_container_time_column_name(self) -> None:
        container = make_time_series_container("a")
        container.init_timeframe(make_daily_df())
        assert container.data.time_name == container.time_column_name  # type: ignore[union-attr]


def _make_config(
    ts_id: str,
    config_id: str = "cfg",
    dep_ts: list[str] | None = None,
    load_dep_ts: list[str] | None = None,
    config_type: ConfigurationType = ConfigurationType.QUALITY_CONTROL,
) -> DataProcessingConfig:
    params: dict = {}
    if dep_ts:
        params["dep_ts"] = dep_ts
    if load_dep_ts:
        params["load_dep_ts"] = load_dep_ts
    return DataProcessingConfig(
        ts_id=ts_id,
        site_id=ts_id + "_site",
        config_id=config_id,
        config_type=config_type,
        method_configs=[DataProcessingMethodConfig(method="m", params=params)],
        annotations={},
    )


class TestLoadOnly:
    def test_load_only_defaults_to_false(self) -> None:
        """Test that load_only is False by default."""
        container = make_time_series_container("a")
        assert container.load_only is False

    def test_load_only_dependencies_returns_empty_when_no_load_dep_ts(self) -> None:
        """Test that load_only_dependencies returns an empty list when no configs have load_dep_ts."""
        container = make_time_series_container("a")
        container.attach_configs([_make_config("a", dep_ts=["b"])])
        assert container.load_only_dependencies() == []

    def test_load_only_dependencies_returns_load_dep_ts_ids(self) -> None:
        """Test that load_only_dependencies returns the load_dep_ts ids from configs."""
        container = make_time_series_container("a")
        container.attach_configs([_make_config("a", load_dep_ts=["L"])])
        assert container.load_only_dependencies() == ["L"]

    def test_load_only_dependencies_aggregates_across_configs(self) -> None:
        """Test that load_only_dependencies deduplicates and aggregates ids across all attached configs."""
        container = make_time_series_container("a")
        container.attach_configs(
            [
                _make_config("a", config_id="qc", load_dep_ts=["L1"]),
                _make_config("a", config_id="corr", dep_ts=["b"]),
                _make_config("a", config_id="inf", load_dep_ts=["L2"]),
                _make_config(
                    "a", config_id="method", load_dep_ts=["L1", "L3"], config_type=ConfigurationType.DERIVATION
                ),
            ]
        )
        assert container.load_only_dependencies() == ["L1", "L2", "L3"]

    def test_is_load_true_when_no_configs_attached(self) -> None:
        """Test that is_load returns True when no data processing configs are attached."""
        container = make_time_series_container("a")
        assert container.is_load() is True

    def test_is_load_false_when_configs_attached(self) -> None:
        """Test that is_load returns False once a data processing config is attached."""
        container = make_time_series_container("a")
        container.attach_configs([_make_config("a")])
        assert container.is_load() is False


class TestAttachConfigs:
    def test_stores_configs_by_config_id(self) -> None:
        """Tests that attach_configs indexes each config under its config_id."""
        container = make_time_series_container("a")
        cfg = _make_config("a", config_id="qc-1")
        container.attach_configs([cfg])
        assert container.data_processing_configs["qc-1"] is cfg

    def test_appends_to_existing_configs(self) -> None:
        """Tests that attaching a second config adds to the dict rather than replacing it."""
        container = make_time_series_container("a")
        cfg1 = _make_config("a", config_id="qc-1")
        cfg2 = _make_config("a", config_id="corr-1", config_type=ConfigurationType.CORRECTION)
        container.attach_configs([cfg1])
        container.attach_configs([cfg2])
        assert "qc-1" in container.data_processing_configs
        assert "corr-1" in container.data_processing_configs

    def test_plan_order_is_independent_of_attach_configs(self) -> None:
        """Tests that plan_order is not set by attach_configs - it must be set separately."""
        container = make_time_series_container("a")
        container.attach_configs([_make_config("a", config_id="qc-1")])
        assert container.plan_order == []
