from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.utils.enums import ConfigurationType


def make_config(params: dict | list[dict], ts_id: str = "ts1") -> DataProcessingConfig:
    if isinstance(params, dict):
        params = [params]
    return DataProcessingConfig(
        ts_id=ts_id,
        site_id="site1",
        config_id="cfg1",
        config_type=ConfigurationType.DERIVATION,
        method_configs=[DataProcessingMethodConfig(method="m", params=p) for p in params],
        annotations={},
    )


class TestValuesForParams:
    def test_single_key_returns_values(self) -> None:
        """Test that values for a single param key are returned as a list."""
        config = make_config({"dep_ts": ["A", "B"]})
        assert config.values_for_params("dep_ts") == ["A", "B"]

    def test_multiple_keys_returns_union(self) -> None:
        """Test that values across multiple param keys are combined into one list."""
        config = make_config({"dep_ts": "A", "load_dep_ts": "B"})
        assert config.values_for_params("dep_ts", "load_dep_ts") == ["A", "B"]

    def test_deduplicates_values_across_keys(self) -> None:
        """Test that duplicate values across different param keys are deduplicated."""
        config = make_config({"dep_ts": "A", "load_dep_ts": "A"})
        assert config.values_for_params("dep_ts", "load_dep_ts") == ["A"]

    def test_returns_empty_when_no_matching_keys(self) -> None:
        """Test that an empty list is returned when no params match the given keys."""
        config = make_config({})
        assert config.values_for_params("dep_ts", "load_dep_ts") == []

    def test_missing_key_returns_empty(self) -> None:
        """Test that a missing param key returns empty list."""
        config = make_config({"dep_ts": ["A", "B"]})
        assert config.values_for_params("load_dep_ts") == []

    def test_aggregates_and_dedupes_across_multiple_method_configs(self) -> None:
        """Test that values are aggregated and deduplicated across multiple method configs."""
        config = DataProcessingConfig(
            ts_id="ts1",
            site_id="site1",
            config_id="cfg1",
            config_type=ConfigurationType.DERIVATION,
            method_configs=[
                DataProcessingMethodConfig(method="m1", params={"load_dep_ts": ["X", "Y"]}),
                DataProcessingMethodConfig(method="m2", params={"load_dep_ts": "Y"}),
            ],
            annotations={},
        )
        assert config.values_for_params("load_dep_ts") == ["X", "Y"]
