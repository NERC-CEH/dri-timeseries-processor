from __future__ import annotations

from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingConfig
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.operations.eddypro.eddypro_run_spec import (
    EddyProColumnSpec,
    EddyProInstrumentSpec,
    EddyProRunSpec,
)
from dritimeseriesprocessor.utils.strings import extract_uri_id


class EddyProMetadataMapper:
    """Map metadata into an EddyPro run spec."""

    def build_run_spec(self, config: DataProcessingConfig, site_metadata: SiteMetadata) -> EddyProRunSpec:
        params = config.method_configs[0].params if config.method_configs else {}

        site_code = site_metadata.alt_id or extract_uri_id(site_metadata.site_id)
        columns = self._map_columns(params)
        instruments = self._map_instruments(params)

        return EddyProRunSpec(
            site_code=site_code,
            software_version=str(params.get("software_version") or params.get("sw_version") or ""),
            file_prototype=str(params.get("file_prototype") or ""),
            master_sonic=str(params.get("master_sonic") or params.get("master_sonic_role") or ""),
            acquisition_frequency=params.get("acquisition_frequency"),
            file_duration=params.get("file_duration"),
            canopy_height=params.get("canopy_height"),
            displacement_height=params.get("displacement_height"),
            roughness_length=params.get("roughness_length"),
            latitude=site_metadata.lat,
            longitude=site_metadata.lon,
            altitude=site_metadata.altitude,
            columns=columns,
            instruments=instruments,
        )

    @staticmethod
    def _strip_prefix(data: dict) -> dict:
        return {(k.split(".", 1)[-1] if "." in k else k): v for k, v in data.items()}

    def _map_columns(self, params: dict) -> list[EddyProColumnSpec]:
        column_items = (
            params.get("column_mapping")
            or (params.get("file_layout") or {}).get("columns")
            or (params.get("file_description") or {}).get("columns")
            or []
        )

        columns: list[EddyProColumnSpec] = []
        for item in column_items:
            item_data = self._strip_prefix(item or {})
            columns.append(
                EddyProColumnSpec(
                    variable=str(item_data.get("variable") or "ignore"),
                    instrument=str(item_data.get("instrument") or item_data.get("instrument_role") or ""),
                    measure_type=str(item_data.get("measure_type") or ""),
                    unit_in=str(item_data.get("unit_in") or ""),
                    min_value=str(item_data.get("min_value") or "0.000000"),
                    max_value=str(item_data.get("max_value") or "0.000000"),
                    conversion=str(item_data.get("conversion") or ""),
                    unit_out=str(item_data.get("unit_out") or ""),
                    a_value=str(item_data.get("a_value") or "1.000000"),
                    b_value=str(item_data.get("b_value") or "0.000000"),
                    nom_timelag=str(item_data.get("nom_timelag") or "0.00"),
                    min_timelag=str(item_data.get("min_timelag") or "0.00"),
                    max_timelag=str(item_data.get("max_timelag") or "0.00"),
                )
            )
        return columns

    def _map_instruments(self, params: dict) -> list[EddyProInstrumentSpec]:
        instrument_items = params.get("instrument_specs") or params.get("instruments") or []
        instruments: list[EddyProInstrumentSpec] = []

        for item in instrument_items:
            item_data = self._strip_prefix(item or {})
            instruments.append(
                EddyProInstrumentSpec(fields={str(k): "" if v is None else str(v) for k, v in item_data.items()})
            )
        return instruments
