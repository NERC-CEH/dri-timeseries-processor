from datetime import datetime

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.operations.eddypro.eddypro_metadata_mapper import EddyProMetadataMapper
from dritimeseriesprocessor.operations.eddypro.eddypro_run_spec import EddyProColumnSpec, EddyProInstrumentSpec


class TestEddyProMetadataMapper:
    def test_build_run_spec_maps_primary_fields(self) -> None:
        mapper = EddyProMetadataMapper()
        config = DataProcessingMethodConfig(
            method="eddypro-run",
            params={
                "software_version": "7.0.9",
                "file_prototype": "TOA5_*.dat",
                "master_sonic": "csat3_1",
                "acquisition_frequency": 20.0,
                "file_duration": 30,
                "canopy_height": 0.2,
                "displacement_height": 0.13,
                "roughness_length": 0.01,
                "column_mapping": [
                    {"column_index": "1", "variable": "u", "instrument": "csat3_1", "unit_in": "m_sec"},
                    {"column_index": "2", "variable": "co2", "instrument_role": "irga", "unit_in": "ppm"},
                ],
                "instrument_specs": [
                    {"manufacturer": "csi", "model": "csat3_1"},
                    {"manufacturer": "licor", "model": None},
                ],
            },
        )
        site_metadata = SiteMetadata(
            site_id="http://fdri.ceh.ac.uk/id/site/flux-plynl",
            network="fdri",
            alt_id="PLYNL",
            lat=52.45,
            lon=-3.75,
            altitude=540.0,
            start_date=datetime(2024, 1, 1),
        )

        result = mapper.build_run_spec(config, site_metadata)

        assert result.site_code == "PLYNL"
        assert result.software_version == "7.0.9"
        assert result.file_prototype == "TOA5_*.dat"
        assert result.master_sonic == "csat3_1"
        assert result.acquisition_frequency == 20.0
        assert result.file_duration == 30
        assert result.canopy_height == 0.2
        assert result.displacement_height == 0.13
        assert result.roughness_length == 0.01
        assert result.latitude == 52.45
        assert result.longitude == -3.75
        assert result.altitude == 540.0
        assert result.columns == [
            EddyProColumnSpec(variable="u", instrument="csat3_1", unit_in="m_sec"),
            EddyProColumnSpec(variable="co2", instrument="irga", unit_in="ppm"),
        ]
        assert result.instruments == [
            EddyProInstrumentSpec(fields={"manufacturer": "csi", "model": "csat3_1"}),
            EddyProInstrumentSpec(fields={"manufacturer": "licor", "model": ""}),
        ]

    def test_build_run_spec_falls_back_to_uri_tail_and_legacy_keys(self) -> None:
        mapper = EddyProMetadataMapper()
        config = DataProcessingMethodConfig(
            method="eddypro-run",
            params={
                "sw_version": "legacy",
                "master_sonic_role": "sonic",
                "file_description": {"columns": [{"column_index": "1", "variable": "ts"}]},
                "instruments": [{"model": "legacy_irga"}],
            },
        )
        site_metadata = SiteMetadata(
            site_id="http://fdri.ceh.ac.uk/id/site/flux-plynl",
            network="fdri",
            alt_id=None,
        )

        result = mapper.build_run_spec(config, site_metadata)

        assert result.site_code == "flux-plynl"
        assert result.software_version == "legacy"
        assert result.master_sonic == "sonic"
        assert result.columns == [EddyProColumnSpec(variable="ts")]
        assert result.instruments == [EddyProInstrumentSpec(fields={"model": "legacy_irga"})]

    def test_build_run_spec_returns_defaults_with_empty_params(self) -> None:
        mapper = EddyProMetadataMapper()
        config = DataProcessingMethodConfig(method="eddypro-run", params={})
        site_metadata = SiteMetadata(
            site_id="http://fdri.ceh.ac.uk/id/site/flux-plynl",
            network="fdri",
            alt_id="PLYNL",
        )

        result = mapper.build_run_spec(config, site_metadata)

        assert result.site_code == "PLYNL"
        assert result.columns == []
        assert result.instruments == []
        assert result.software_version == ""
