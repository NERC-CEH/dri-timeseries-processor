from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
from isoperiod import Period
from polars.testing import assert_frame_equal

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.operations.derivation.derivation_methods import (
    DerivationMethod,
    GetPrecipTipping,
    GetSnowEstimatedCounts,
    NetRadiation,
    SolarZenith,
    VolumetricWaterContent,
    VolumetricWaterContentWithSnow,
)
from dritimeseriesprocessor.operations.eddypro.eddypro_run_method import EddyProRun
from utils.data_creation import dataframe_to_timeframe


class SimpleAddition(DerivationMethod):
    name = "add"
    inputs = ("a", "b")

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return columns["a"] + columns["b"]


class AddAnnotationAttribute(DerivationMethod):
    name = "add_annotation_attribute"
    inputs = ("a",)

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return columns["a"] + columns["saturation"]


class AddDeploymentAttribute(DerivationMethod):
    name = "add_deployment_attribute"
    inputs = ("a",)

    def expr(self, columns: dict[str, pl.Expr]) -> pl.Expr:
        return columns["a"] + columns["sensor_height"]


def create_method_config(
    data: Mapping[str, Sequence[float | None]],
    output_col: str,
) -> DataProcessingMethodConfig:
    """Create a test MethodConfig.

    Args:
        data: List of data objects needed for the calculation
        output_col: Name of the output column expected in the result
        argument: Dict of arguments to add to the config

    Returns:
        MethodConfig for testing
    """
    params: dict[str, Any] = {}
    if data:
        params = {
            column_name: dataframe_to_timeframe(
                df=pl.DataFrame({column_name: values}),
                metadata={"column_name": column_name},
            )
            for column_name, values in data.items()
        }
    params["output_col"] = output_col
    params["periodicity"] = "PT1H"
    params["resolution"] = "PT1H"
    params["time_anchor"] = "start"

    return DataProcessingMethodConfig(method="test", params=params)


class TestDerivationMethod:
    def test_run_simple_addition_calculation(self) -> None:
        """Test a simple addition derivation workflow"""
        method = SimpleAddition()
        config = create_method_config({"a": [10.0, 20.0, 30.0], "b": [5.0, 10.0, 15.0]}, "out")

        result = method.run(None, config)
        expected = dataframe_to_timeframe(pl.DataFrame({"out": [15.0, 30.0, 45.0]}), metadata={"column_name": "out"})
        assert result == expected

    def test_join_annotation_attributes_joins_time_variable_site_annotation(self) -> None:
        """Tests that a time-variable site annotation param is joined onto the calculation as a column."""
        method = AddAnnotationAttribute()
        config = create_method_config({"a": [1.0, 2.0, 3.0]}, "out")
        config.params["saturation"] = [(datetime(2025, 1, 1), None, 10.0)]

        result = method.run(None, config)
        expected = dataframe_to_timeframe(pl.DataFrame({"out": [11.0, 12.0, 13.0]}), metadata={"column_name": "out"})
        assert result == expected

    def test_join_deployment_attributes_joins_time_bound_deployment_value(self) -> None:
        """Tests that a deployment attribute param is joined onto the calculation as a column."""
        method = AddDeploymentAttribute()
        config = create_method_config({"a": [1.0, 2.0, 3.0]}, "out")
        config.params["sensor_height"] = {
            "sensor_height.source": "deployment",
            "sensor_height.value": [(datetime(2025, 1, 1), None, 2.0)],
        }

        result = method.run(None, config)
        expected = dataframe_to_timeframe(pl.DataFrame({"out": [3.0, 4.0, 5.0]}), metadata={"column_name": "out"})
        assert result == expected

    def test_result_keeps_only_the_output_column(self) -> None:
        """Tests that the input columns are dropped, leaving the time column and the output column."""
        method = SimpleAddition()
        config = create_method_config({"a": [10.0, 20.0], "b": [5.0, 10.0]}, "out")

        result = method.run(None, config)
        assert result.df.columns == ["time", "out"]
        assert result.metadata["column_name"] == "out"

    def test_result_takes_its_time_properties_from_the_config(self) -> None:
        """Tests that resolution, periodicity and time anchor on the result come from the config params."""
        method = SimpleAddition()
        config = create_method_config({"a": [10.0, 20.0], "b": [5.0, 10.0]}, "out")
        config.params["resolution"] = "PT30M"
        config.params["periodicity"] = "P1D"
        config.params["time_anchor"] = "end"

        result = method.run(None, config)
        assert result.resolution == Period.of_minutes(30)
        assert result.periodicity == Period.of_days(1)
        assert result.time_anchor == "end"

    def test_scalar_params_are_not_treated_as_input_data(self) -> None:
        """Tests that only the TimeFrame params are merged as inputs, so scalars are left out of the data."""
        method = SimpleAddition()
        config = create_method_config({"a": [10.0, 20.0], "b": [5.0, 10.0]}, "out")
        config.params["some_site_value"] = 42.0

        result = method.run(None, config)
        assert result.df.columns == ["time", "out"]

    def test_method_is_looked_up_by_its_registered_name(self) -> None:
        """Tests that the name in a processing config resolves to the matching derivation class."""
        assert isinstance(DerivationMethod.get("calculate_rn"), NetRadiation)


class TestSolarZenith:
    def test_time_values_come_from_the_swin_input(self) -> None:
        """Tests that the angle is calculated per time step, using the time column of the swin input."""
        config = create_method_config({"swin": [0.0] * 24}, "solar_zenith")
        config.params["lat"] = 54.110665

        result = SolarZenith().run(None, config)
        angles = result.df["solar_zenith"].to_list()

        # swin itself is constant, so any variation can only have come from the time column.
        assert len(angles) == 24
        assert None not in angles
        assert len(set(angles)) > 1


class TestVolumetricWaterContentWithSnow:
    def test_snow_period_counts_take_precedence_over_corrected_counts(self) -> None:
        """Tests that the snow count estimate is used where there is one, and the corrected counts elsewhere."""
        cts_mod_corr = [1000.0, 1300.0, 1500.0, 1800.0]
        cts_est_crns = [None, 1500.0, None, 2000.0]
        site_annotations = {
            "n0_mod": 2710.16689,
            "ref_bulkdensity": 1.06,
            "ref_latticewater": 0.025,
            "ref_soc": 0.032,
            "n_min": 1204.50827,
            "n_max": 2281.33025,
        }

        config = create_method_config({"cts_mod_corr": cts_mod_corr, "cts_est_crns": cts_est_crns}, "vwc")
        config.params.update(site_annotations)
        result = VolumetricWaterContentWithSnow().run(None, config)

        # The same calculation, given the counts the fallback should have chosen.
        expected_counts = [est if est is not None else corr for est, corr in zip(cts_est_crns, cts_mod_corr)]
        expected_config = create_method_config({"cts_mod_corr": expected_counts}, "vwc")
        expected_config.params.update(site_annotations)
        expected = VolumetricWaterContent().run(None, expected_config)

        assert_frame_equal(result.df, expected.df)


class TestGetSnowEstimatedCounts:
    def test_daily_snow_is_broadcast_onto_the_hourly_counts(self) -> None:
        """Tests that each day's snow flag is joined onto every hourly count row for that date."""
        snow_by_day = [True, False, True]
        params = {
            "cts_smo_crns": dataframe_to_timeframe(
                df=pl.DataFrame({"CTS_SMO_CRNS": [1000.0] * 72}),
                metadata={"column_name": "CTS_SMO_CRNS"},
            ),
            "snow": dataframe_to_timeframe(
                df=pl.DataFrame({"SNOW": snow_by_day, "time": [datetime(2025, 1, day) for day in range(1, 4)]}),
                metadata={"column_name": "SNOW"},
                resolution="P1D",
            ),
        }
        config = DataProcessingMethodConfig(method="test", params=params)
        tf_map = {name: timeframe for name, timeframe in params.items()}
        columns = {name: pl.col(timeframe.metadata["column_name"]) for name, timeframe in tf_map.items()}

        columns, merged_tf = GetSnowEstimatedCounts().merge_inputs(config, tf_map, columns)

        assert merged_tf.df["SNOW"].to_list() == [flag for flag in snow_by_day for _ in range(24)]
        assert merged_tf.df.height == 72
        assert "time" in columns

    @pytest.mark.parametrize(
        ("cts_smo_resolution", "snow_resolution", "expected_message"),
        [
            ("P1D", "P1D", "Resolution of cts_smo_crns must be hourly"),  # cts_smo_crns should be hourly, not daily
            ("PT1H", "PT1H", "Resolution of snow must be daily"),  # snow should be daily, not hourly
        ],
    )
    def test_raises_when_periodicities_are_incorrect(
        self, cts_smo_resolution: str, snow_resolution: str, expected_message: str
    ) -> None:
        """Test a ValueError is raised if cts_smo_crns is not hourly, or snow is not daily."""
        params = {
            "cts_smo_crns": dataframe_to_timeframe(
                df=pl.DataFrame(
                    {
                        "CTS_SMO_CRNS": [995.0, 1000, 1002, 995],
                        "time": [datetime(2025, 1, i) for i in range(1, 5)],
                    }
                ),
                metadata={"column_name": "CTS_SMO_CRNS"},
                resolution=cts_smo_resolution,
            ),
            "snow": dataframe_to_timeframe(
                df=pl.DataFrame(
                    {
                        "SNOW": [True, False, False, True],
                        "time": [datetime(2025, 1, i) for i in range(1, 5)],
                    }
                ),
                metadata={"column_name": "SNOW"},
                resolution=snow_resolution,
            ),
            "output_col": "cts_est_crns",
            "periodicity": "PT1H",
            "resolution": "PT1H",
            "time_anchor": "start",
        }

        config = DataProcessingMethodConfig(method="test", params=params)

        with pytest.raises(ValueError, match=expected_message):
            GetSnowEstimatedCounts().run(None, config)


class TestGetPrecipTipping:
    def test_consolidates_equal_values(self) -> None:
        """Tests that equal A and B values are consolidated to that same value."""
        config = create_method_config(
            {"precip_tipping_a": [0.2, 1.0], "precip_tipping_b": [0.2, 1.0]},
            "precip_tipping",
        )
        result = GetPrecipTipping().run(None, config)
        assert list(result.df["precip_tipping"]) == [0.2, 1.0]

    def test_consolidates_to_higher_value_when_not_equal(self) -> None:
        """Tests that the higher of A and B is picked when they differ."""
        config = create_method_config(
            {"precip_tipping_a": [0.2, 1.5], "precip_tipping_b": [0.6, 1.0]},
            "precip_tipping",
        )
        result = GetPrecipTipping().run(None, config)
        assert list(result.df["precip_tipping"]) == [0.6, 1.5]

    def test_null_in_one_gauge_returns_non_null_value(self) -> None:
        """Tests that a null in one gauge falls back to the non-null value from the other."""
        config = create_method_config(
            {"precip_tipping_a": [None, 0.4], "precip_tipping_b": [0.4, None]},
            "precip_tipping",
        )
        result = GetPrecipTipping().run(None, config)
        assert list(result.df["precip_tipping"]) == [0.4, 0.4]

    def test_null_in_both_gauges_returns_null(self) -> None:
        """Tests that a null in both gauges is treated as equivalent and returns null."""
        config = create_method_config(
            {"precip_tipping_a": [None], "precip_tipping_b": [None]},
            "precip_tipping",
        )
        result = GetPrecipTipping().run(None, config)
        assert result.df["precip_tipping"][0] is None


def _make_eddypro_config(
    container: MagicMock,
    dataset_repository: dict,
    start_date: datetime = datetime(2024, 1, 1),
    end_date: datetime = datetime(2024, 1, 31),
    site_metadata: dict | None = None,
    file_duration: int = 30,
) -> DataProcessingMethodConfig:
    return DataProcessingMethodConfig(
        method="eddypro-run",
        params={
            "container": container,
            "dataset_repository": dataset_repository,
            "processing_start_date": start_date,
            "processing_end_date": end_date,
            "site_metadata": site_metadata or {},
            "file_duration": file_duration,
        },
    )


class TestEddyProRun:
    def test_raises_when_no_base_dependency(self) -> None:
        """Tests that a ValueError is raised when the container has no base dependency."""
        container = MagicMock()
        container.base_dependency = []

        config = _make_eddypro_config(container, {})

        with pytest.raises(ValueError):
            EddyProRun().run(None, config)

    def test_raises_when_multiple_base_dependencies(self) -> None:
        """Tests that a ValueError is raised when the container has more than one base dependency."""
        container = MagicMock()
        container.base_dependency = ["dep-1", "dep-2"]

        config = _make_eddypro_config(container, {"dep-1": MagicMock(), "dep-2": MagicMock()})

        with pytest.raises(ValueError):
            EddyProRun().run(None, config)

    def test_raises_when_staged_dir_is_none(self) -> None:
        """Tests that a ValueError is raised when the raw dependency has not been staged locally."""
        container = MagicMock()
        container.base_dependency = ["raw-dep"]
        raw_dep = MagicMock()
        raw_dep.staged_dir = None
        raw_dep.ts_id = "raw-dep"

        config = _make_eddypro_config(container, {"raw-dep": raw_dep})

        with pytest.raises(ValueError):
            EddyProRun().run(None, config)

    def test_calls_pipeline_with_staged_dir_and_date_range(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Tests that EddyProPipeline.run is called with the raw staged directory and the date range."""
        container = MagicMock()
        container.base_dependency = ["raw-dep"]
        container.all_dependencies.return_value = ["raw-dep"]
        container.source_site = "flux-plynl"
        raw_dep = MagicMock()
        raw_dep.staged_dir = tmp_path
        raw_dep.ts_id = "raw-dep"

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = pl.DataFrame({"time": []})
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.eddypro.eddypro_run_method.EddyProRunner",
            MagicMock,
        )
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.eddypro.eddypro_run_method.EddyProPipeline",
            lambda *args, **kwargs: mock_pipeline,
        )

        EddyProRun().run(None, _make_eddypro_config(container, {"raw-dep": raw_dep}, start_date=start, end_date=end))

        call_kwargs = mock_pipeline.run.call_args.kwargs
        assert call_kwargs["raw_data_dir"] == tmp_path
        assert call_kwargs["start_date"] == start
        assert call_kwargs["end_date"] == end

    def test_sets_container_resolution_from_file_duration(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Tests that the container's resolution and periodicity are set from the file_duration param."""
        container = MagicMock()
        container.base_dependency = ["raw-dep"]
        container.all_dependencies.return_value = ["raw-dep"]
        container.source_site = "flux-plynl"
        raw_dep = MagicMock()
        raw_dep.staged_dir = tmp_path
        raw_dep.ts_id = "raw-dep"

        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = pl.DataFrame({"time": []})
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.eddypro.eddypro_run_method.EddyProRunner",
            MagicMock,
        )
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.eddypro.eddypro_run_method.EddyProPipeline",
            lambda *args, **kwargs: mock_pipeline,
        )

        EddyProRun().run(None, _make_eddypro_config(container, {"raw-dep": raw_dep}, file_duration=30))

        assert container.time_column_name == "time"
        assert container.resolution == "PT30M"
        assert container.periodicity == container.resolution

    def test_returns_container_data(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Tests that the method returns the container's data after init_timeframe is called."""
        container = MagicMock()
        container.base_dependency = ["raw-dep"]
        container.all_dependencies.return_value = ["raw-dep"]
        container.source_site = "flux-plynl"
        raw_dep = MagicMock()
        raw_dep.staged_dir = tmp_path
        raw_dep.ts_id = "raw-dep"

        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = pl.DataFrame({"time": []})
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.eddypro.eddypro_run_method.EddyProRunner",
            MagicMock,
        )
        monkeypatch.setattr(
            "dritimeseriesprocessor.operations.eddypro.eddypro_run_method.EddyProPipeline",
            lambda *args, **kwargs: mock_pipeline,
        )

        result = EddyProRun().run(None, _make_eddypro_config(container, {"raw-dep": raw_dep}))

        container.init_timeframe.assert_called_once()
        assert result == container.data
