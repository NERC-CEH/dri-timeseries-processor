"""
Domain model representing a "core" method for a time series in the FDRI system.

A core method is defined as one of:

- LOAD = load raw data
- PROCESS = carry out standard processing steps
- DERIVATION = derive / calculate a new variable using an equation
- AGGREGATION = derive a new variable by aggregating an existing variable
"""

from dataclasses import dataclass

from new_processor.utils.enums import MethodType


@dataclass
class MethodConfig:
    method_type: MethodType
    config_id: str | None = None
    name: str | None = None
