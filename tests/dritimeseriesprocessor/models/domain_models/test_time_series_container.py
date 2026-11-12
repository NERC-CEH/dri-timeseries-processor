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
    group_by_access_url,
)
from dritimeseriesprocessor.utils.enums import ConfigurationType, ProcessingLevel
from utils.data_creation import make_time_series_container


def make_daily_df(n_rows: int = 3, col_name: str = "value") -> pl.DataFrame:
    dates = [datetime(2025, 1, 1) + timedelta(days=i) for i in range(n_rows)]
    return pl.DataFrame({"time": dates, col_name: list(range(n_rows))})


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
            ProcessingLevel.RAW,
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


class TestGroupByAccessUrl:
    def test_empty_containers_returns_empty_dict(self) -> None:
        """Tests that grouping no containers gives an empty dictionary."""
        assert group_by_access_url(()) == {}

    def test_containers_with_same_url_are_grouped_together(self) -> None:
        """Tests that containers sharing an access URL end up in one group, keyed by that URL."""
        container_a = make_time_series_container("a")
        container_b = make_time_series_container("b")
        container_a.access_url = container_b.access_url = "s3://bucket/network=X/collection=Y/site=Z"

        result = group_by_access_url((container_a, container_b))

        assert result == {"s3://bucket/network=X/collection=Y/site=Z": [container_a, container_b]}

    def test_containers_with_different_urls_are_grouped_separately(self) -> None:
        """Tests that each access URL gets its own group, keeping the containers in their original order."""
        container_a1 = make_time_series_container("a1")
        container_b = make_time_series_container("b")
        container_a2 = make_time_series_container("a2")
        container_a1.access_url = container_a2.access_url = "s3://bucket/collection=A"
        container_b.access_url = "s3://bucket/collection=B"

        result = group_by_access_url((container_a1, container_b, container_a2))

        assert result == {
            "s3://bucket/collection=A": [container_a1, container_a2],
            "s3://bucket/collection=B": [container_b],
        }

    def test_containers_with_no_url_are_grouped_under_none(self) -> None:
        """Tests that containers with no access URL are grouped together under None."""
        container_a = make_time_series_container("a")
        container_b = make_time_series_container("b")
        container_a.access_url = None
        container_b.access_url = None

        assert group_by_access_url((container_a, container_b)) == {None: [container_a, container_b]}


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
        assert container.data.metadata == {"column_name": container.source_column, "unit": container.unit}  # type: ignore[union-attr]

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
