"""
Models for resolving dataset selection intent for processing runs, originating from the CLI (or potentially
other entry points), and the run configuration for each run mode.
"""

from dataclasses import dataclass
from datetime import datetime


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
class NetworkSitesSelection:
    """A network, and optionally some of its sites by name. If no sites are given, all sites in the network are used."""

    network: str
    sites: list[str] | None = None

    def __repr__(self) -> str:
        return f"network={self.network} | sites={', '.join(self.sites) if self.sites else 'ALL'}"

    def __hash__(self) -> int:
        sites_str = "/".join(self.sites or [""])
        return hash(f"{self.network}{sites_str}")


class ListSitesSelection(NetworkSitesSelection):
    """Represents a request to list sites for a network. If `sites` is given, only those sites are considered
    (still checked for network membership); otherwise all sites for the network are listed."""


class HistoricSelection(NetworkSitesSelection):
    """Represents a request to process everything for a network's sites over each site's full operating dates."""


# A selection of datasets to process, as accepted by the dependency graph.
# ListSitesSelection and HistoricSelection are left out as they never reach the dependency graph.
Selection = DimensionSelection | DatasetIdSelection


@dataclass(frozen=True)
class StandardRunConfig:
    """Runtime configuration for processing the selected datasets over a date range."""

    selection: list[Selection]
    start_date: datetime
    end_date: datetime


@dataclass(frozen=True)
class HistoricRunConfig:
    """Runtime configuration for processing a network's sites over each site's full operating dates."""

    selection: HistoricSelection


@dataclass(frozen=True)
class ListSitesRunConfig:
    """Runtime configuration for listing a network's sites that were open during a date range.

    With no dates, every site the network has ever had is listed.
    """

    selection: ListSitesSelection
    start_date: datetime | None
    end_date: datetime | None


# Collects user intent for a run. Each mode has its own type, holding only what that mode needs.
RunConfig = StandardRunConfig | HistoricRunConfig | ListSitesRunConfig
