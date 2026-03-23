from dritimeseriesprocessor.operations.eddypro.eddypro_run_spec import (
    EddyProColumnSpec,
    EddyProInstrumentSpec,
    EddyProRunSpec,
)


class TestEddyProRunSpec:
    def test_column_spec_defaults(self) -> None:
        spec = EddyProColumnSpec()

        assert spec.variable == "ignore"
        assert spec.instrument == ""
        assert spec.unit_in == ""
        assert spec.min_value == "0.000000"
        assert spec.max_value == "0.000000"
        assert spec.a_value == "1.000000"
        assert spec.b_value == "0.000000"
        assert spec.nom_timelag == "0.00"

    def test_instrument_spec_defaults(self) -> None:
        spec = EddyProInstrumentSpec()

        assert spec.fields == {}

    def test_run_spec_defaults(self) -> None:
        spec = EddyProRunSpec(site_code="PLYNL")

        assert spec.site_code == "PLYNL"
        assert spec.software_version == ""
        assert spec.file_prototype == ""
        assert spec.master_sonic == ""
        assert spec.acquisition_frequency is None
        assert spec.file_duration is None
        assert spec.canopy_height is None
        assert spec.displacement_height is None
        assert spec.roughness_length is None
        assert spec.latitude is None
        assert spec.longitude is None
        assert spec.altitude is None
        assert spec.columns == []
        assert spec.instruments == []
