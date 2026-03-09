from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EddyProColumnSpec:
    variable: str = "ignore"
    instrument: str = ""
    measure_type: str = ""
    unit_in: str = ""
    min_value: str = "0.000000"
    max_value: str = "0.000000"
    conversion: str = ""
    unit_out: str = ""
    a_value: str = "1.000000"
    b_value: str = "0.000000"
    nom_timelag: str = "0.00"
    min_timelag: str = "0.00"
    max_timelag: str = "0.00"


@dataclass(frozen=True)
class EddyProInstrumentSpec:
    fields: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EddyProRunSpec:
    site_code: str
    software_version: str = ""
    file_prototype: str = ""
    master_sonic: str = ""
    acquisition_frequency: float | int | None = None
    file_duration: int | None = None
    canopy_height: float | int | None = None
    displacement_height: float | int | None = None
    roughness_length: float | int | None = None
    latitude: float | int | None = None
    longitude: float | int | None = None
    altitude: float | int | None = None
    columns: list[EddyProColumnSpec] = field(default_factory=list)
    instruments: list[EddyProInstrumentSpec] = field(default_factory=list)
