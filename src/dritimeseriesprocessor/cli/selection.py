"""
Models for resolving dataset selection intent for processing runs, originating from the CLI (or potentially
other entry points)
"""

from dataclasses import dataclass
from datetime import datetime

from dritimeseriesprocessor.utils.enums import CliSelectionMode


@dataclass(frozen=True)
class SelectionOption:
    """Represents a selection of dataset dimension combinations."""

    sites: list[str] | None = None
    variables: list[str] | None = None
    periodicities: list[str] | None = None

    def __repr__(self) -> str:
        return (
            f"sites={self._fmt_dim(self.sites)} | "
            f"variables={self._fmt_dim(self.variables)} | "
            f"periodicities={self._fmt_dim(self.periodicities)}"
        )

    @staticmethod
    def _fmt_dim(values: list[str] | None) -> str:
        if values is None:
            return "ALL"
        if not values:
            return "NONE"
        return ", ".join(values)

    def __hash__(self) -> int:
        """Allow this object to be used as a dict or set key."""
        sites_str = "/".join(self.sites or [""])
        variables_str = "/".join(self.variables or [""])
        periodicities_str = "/".join(self.periodicities or [""])
        return hash(f"{sites_str}{variables_str}{periodicities_str}")


@dataclass(frozen=True)
class RunConfig:
    """Runtime configuration object for a processing run. This collects user intent, including dataset selection
    constraints and the temporal processing window. It serves as the boundary between CLI parsing and runtime execution.
    """

    network: str
    selection: list[SelectionOption]
    start_date: datetime
    end_date: datetime
    mode: CliSelectionMode
