"""
Models for resolving dataset selection intent for processing runs, originating from the CLI (or potentially
other entry points)
"""

from dataclasses import dataclass
from datetime import datetime

from dritimeseriesprocessor.utils.enums import CliSelectionMode


@dataclass(frozen=True)
class DimensionSelection:
    """Represents a selection of dataset dimension combinations (site, variable, periodicity)."""

    network: str
    sites: list[str] | None = None
    variables: list[str] | None = None
    periodicities: list[str] | None = None

    def __repr__(self) -> str:
        return (
            f"network={self.network} | "
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
        return hash(f"{self.network}{sites_str}{variables_str}{periodicities_str}")


@dataclass(frozen=True)
class DatasetIdSelection:
    """Represents an explicit list of dataset IDs to process."""

    dataset_ids: list[str]

    def __repr__(self) -> str:
        return f"datasets={', '.join(self.dataset_ids)}"

    def __hash__(self) -> int:
        return hash("/".join(self.dataset_ids))


@dataclass(frozen=True)
class ListSitesSelection:
    """Represents a request to list all sites for a network."""

    network: str

    def __repr__(self) -> str:
        return f"network={self.network}"

    def __hash__(self) -> int:
        return hash(self.network)


Selection = DimensionSelection | DatasetIdSelection | ListSitesSelection


@dataclass(frozen=True)
class RunConfig:
    """Runtime configuration object for a processing run. This collects user intent, including dataset selection
    constraints and the temporal processing window. It serves as the boundary between CLI parsing and runtime execution.
    """

    selection: list[Selection]
    start_date: datetime
    end_date: datetime
    mode: CliSelectionMode
