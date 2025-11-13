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

from new_processor.utils.enums import ConfigurationType


@dataclass
class MethodConfig:
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    start_date: datetime | None = None
    end_date: datetime | None = None


@dataclass
class ProcessingConfig:
    ts_id: str
    config_id: str
    config_type: ConfigurationType
    method_configs: list[MethodConfig]
    annotations: dict[str, Any] = field(default_factory=dict)

    def all_dep_ts(self) -> list[str]:
        deps = set()
        for method_config in self.method_configs:
            if "dep_ts" in method_config.params:
                dep_ts_ids = method_config.params["dep_ts"]
                if isinstance(dep_ts_ids, list):
                    deps.update(dep_ts_ids)
                else:
                    deps.add(dep_ts_ids)
        return sorted(deps)
