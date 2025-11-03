"""
Domain models representing a processing configuration and associated method configurations for a time series
in the FDRI system.

A processing configuration could be for: Quality control, Infilling, or Correction.

Most of the time, each processing configuration will have one method configuration, however there is the
possibility that there may be multiple - for example if different method configurations apply to different
slices of the time series.  Use "start_date" and "end_date" to determine this.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.new_processor.enums import ConfigurationType


@dataclass
class MethodConfig:
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    start_date: datetime | None = None
    end_date: datetime | None = None


@dataclass
class ProcessingConfig:
    config_id: str
    config_type: ConfigurationType
    method_configs: list[MethodConfig]
    annotations: dict[str, Any] = field(default_factory=dict)

    def all_dep_ts(self) -> list[str]:
        dep_ts = []
        for method_config in self.method_configs:
            if "dep_ts" in method_config.params:
                dep_ts.append(method_config.params["dep_ts"])
        return dep_ts
