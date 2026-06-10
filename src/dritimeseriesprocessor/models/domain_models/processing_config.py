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

from dritimeseriesprocessor.utils.enums import ConfigurationType


@dataclass
class DataProcessingMethodConfig:
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    start_date: datetime | None = None
    end_date: datetime | None = None


@dataclass
class DataProcessingConfig:
    ts_id: str
    config_id: str
    config_type: ConfigurationType
    method_configs: list[DataProcessingMethodConfig]
    annotations: dict[str, Any] = field(default_factory=dict)

    def values_for_params(self, *keys: str) -> list[str]:
        """Collect and deduplicate values from the given parameter keys across all method configs.

        Args:
            keys: One or more parameter key names to extract values from (e.g. `dep_ts`, `load_dep_ts`).

        Returns:
            Sorted, deduplicated list of values found across all method configs for the given keys.
        """
        values: set[str] = set()
        for method_config in self.method_configs:
            for key in keys:
                if key in method_config.params:
                    v = method_config.params[key]
                    if isinstance(v, list):
                        values.update(v)
                    else:
                        values.add(v)
        return sorted(values)

    def __hash__(self) -> int:
        """Allow this container to be used as a dict or set key."""
        return hash(self.ts_id + "_" + self.config_id)
