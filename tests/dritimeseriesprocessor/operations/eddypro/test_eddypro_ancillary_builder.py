from datetime import datetime
from pathlib import Path

import polars as pl
import pytest
import time_stream as ts

from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.operations.eddypro.eddypro_ancillary_builder import (
    EddyProBiometBuilder,
    EddyProDynamicMetadataBuilder,
)
from dritimeseriesprocessor.utils.enums import ProcessingLevel


def make_container(
    ts_id: str,
    source_column: str,
    df: pl.DataFrame | None = None,
    periodicity: str = "PT30M",
    time_column_name: str = "time",
) -> TimeSeriesContainer:
    container = TimeSeriesContainer(
        ts_id=ts_id,
        network="fdri",
        source_bucket="bucket",
        source_dataset="dataset",
        source_column=source_column,
        source_site="PLYNL",
        source_site_identifier="PLYNL",
        time_column_name=time_column_name,
        unit=None,
        resolution=periodicity,
        periodicity=periodicity,
        time_anchor="start",
        processing_level=ProcessingLevel.PROCESSED,
    )
    if df is not None:
        container.data = ts.TimeFrame(
            df=df,
            time_name=time_column_name,
            resolution=periodicity,
            periodicity=periodicity,
        )
    return container


class TestEddyProBiometBuilder:
    def test_build_writes_biomet_csv_with_expected_order_and_pre_aggregated_values(self, tmp_path: Path) -> None:
        builder = EddyProBiometBuilder()

        air_temp = make_container(
            ts_id="air-temp",
            source_column="AirTemp_C",
            df=pl.DataFrame(
                {
                    "time": [datetime(2026, 1, 20, 0, 0), datetime(2026, 1, 20, 0, 30)],
                    "AirTemp_C": [10.611, 12.611],
                }
            ),
        )
        relative_humidity = make_container(
            ts_id="rh",
            source_column="RH",
            df=pl.DataFrame(
                {
                    "time": [datetime(2026, 1, 20, 0, 0), datetime(2026, 1, 20, 0, 30)],
                    "RH": [80.111, 81.222],
                }
            ),
        )
        unsupported = make_container(
            ts_id="unsupported",
            source_column="not_supported",
            df=pl.DataFrame(
                {
                    "time": [datetime(2026, 1, 20, 0, 0)],
                    "not_supported": [1.0],
                }
            ),
        )

        output_path = builder.build(
            containers=[relative_humidity, unsupported, air_temp],
            output_path=tmp_path / "inputs" / "biomet.csv",
        )

        assert output_path.name == "biomet.csv"
        assert output_path.read_text().splitlines() == [
            "TIMESTAMP_1,AirTemp_C,RH",
            "yyyy-mm-dd HH:MM,-,-",
            "2026-01-20 00:00,10.61,80.11",
            "2026-01-20 00:30,12.61,81.22",
        ]

    def test_build_raises_when_no_usable_data(self, tmp_path: Path) -> None:
        no_data = make_container(ts_id="air-temp", source_column="AirTemp_C")

        with pytest.raises(ValueError, match="No usable biomet data"):
            EddyProBiometBuilder().build(
                containers=[no_data],
                output_path=tmp_path / "biomet.csv",
            )

    def test_build_raises_when_no_supported_containers(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="No usable biomet data"):
            EddyProBiometBuilder().build(
                containers=[],
                output_path=tmp_path / "biomet.csv",
            )

    def test_build_includes_null_column_for_container_with_no_data(self, tmp_path: Path) -> None:
        air_temp = make_container(
            ts_id="air-temp",
            source_column="AirTemp_C",
            df=pl.DataFrame(
                {
                    "time": [datetime(2026, 1, 20, 0, 0)],
                    "AirTemp_C": [10.0],
                }
            ),
        )
        rh_no_data = make_container(ts_id="rh", source_column="RH")

        output_path = EddyProBiometBuilder().build(
            containers=[air_temp, rh_no_data],
            output_path=tmp_path / "biomet.csv",
        )

        lines = output_path.read_text().splitlines()
        assert lines[0] == "TIMESTAMP_1,AirTemp_C,RH"


class TestEddyProDynamicMetadataBuilder:
    def test_build_writes_dynamic_metadata_with_expected_units_and_order(self, tmp_path: Path) -> None:
        builder = EddyProDynamicMetadataBuilder()

        canopy_height = make_container(
            ts_id="canopy-height",
            source_column="height_canopy",
            df=pl.DataFrame(
                {
                    "time": [datetime(2026, 1, 20, 0, 0), datetime(2026, 1, 20, 0, 30)],
                    "height_canopy": [0.52, 0.61],
                }
            ),
        )
        sonic_azimuth = make_container(
            ts_id="sonic-azimuth",
            source_column="sonic_azimuth",
            df=pl.DataFrame(
                {
                    "time": [datetime(2026, 1, 20, 0, 0), datetime(2026, 1, 20, 0, 30)],
                    "sonic_azimuth": [12.0, 14.5],
                }
            ),
        )
        unsupported = make_container(
            ts_id="unsupported",
            source_column="wind_speed",
            df=pl.DataFrame(
                {
                    "time": [datetime(2026, 1, 20, 0, 0)],
                    "wind_speed": [1.2],
                }
            ),
        )

        output_path = builder.build(
            containers=[canopy_height, unsupported, sonic_azimuth],
            output_path=tmp_path / "inputs" / "dynamic_metadata.txt",
        )

        assert output_path.name == "dynamic_metadata.txt"  # type: ignore[union-attr]
        assert output_path.read_text().splitlines() == [  # type: ignore[union-attr]
            "date\ttime\tsonic_azimuth\theight_canopy",
            "yyyy-mm-dd\tHH:MM\tdeg\tm",
            "2026-01-20\t00:00\t12.0\t0.52",
            "2026-01-20\t00:30\t14.5\t0.61",
        ]

    def test_build_returns_none_when_no_usable_data(self, tmp_path: Path) -> None:
        no_data = make_container(ts_id="sonic-azimuth", source_column="sonic_azimuth")

        result = EddyProDynamicMetadataBuilder().build(
            containers=[no_data],
            output_path=tmp_path / "dynamic_metadata.txt",
        )

        assert result is None
        assert not (tmp_path / "dynamic_metadata.txt").exists()

    def test_build_returns_none_when_no_supported_containers(self, tmp_path: Path) -> None:
        result = EddyProDynamicMetadataBuilder().build(
            containers=[],
            output_path=tmp_path / "dynamic_metadata.txt",
        )

        assert result is None

    def test_build_preserves_partial_rows(self, tmp_path: Path) -> None:
        sonic_azimuth = make_container(
            ts_id="sonic-azimuth",
            source_column="sonic_azimuth",
            df=pl.DataFrame(
                {
                    "time": [datetime(2026, 1, 20, 0, 0), datetime(2026, 1, 20, 0, 30)],
                    "sonic_azimuth": [12.0, 14.5],
                }
            ),
        )
        # height_canopy has no data - rows should still appear (partial row, not dropped)
        height_no_data = make_container(ts_id="height-canopy", source_column="height_canopy")

        output_path = EddyProDynamicMetadataBuilder().build(
            containers=[sonic_azimuth, height_no_data],
            output_path=tmp_path / "dynamic_metadata.txt",
        )

        lines = output_path.read_text().splitlines()  # type: ignore[union-attr]
        assert lines[0] == "date\ttime\tsonic_azimuth\theight_canopy"
        assert len(lines) == 4  # header + units + 2 data rows
