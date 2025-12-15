"""
Models for resolving dataset selection intent for processing runs, originating from the CLI (or potentially
other entry points)

This selection layer is intentionally free of infrastructure concerns. It does not perform metadata lookups or
dataset discovery. Instead, it's goal is to structure user intent into usable objects that can be used in the
runtime components, such as the DatasetDependencyGraph

Two selection modes are supported:
- Explicit selection: A fixed list of dataset keys
- Cross-product selection: Cross-product combinations of  sites, variables, and periodicities.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Iterable


@dataclass(frozen=True)
class DatasetKey:
    """Identifier for a single dataset dimension combination."""

    site: str
    variable: str
    periodicity: str


class SelectionSpec(ABC):
    """Abstract base class for dataset selection specifications - capturing user intent regarding which datasets
    should be processed.
    """

    @abstractmethod
    def resolve(self) -> Iterable:
        """Resolve the selection specification into concrete constraints.

        Returns:
            A tuple of (sites, variables, periodicities). Empty lists indicate unconstrained dimensions and should
            be interpreted as "all" by downstream components.
        """
        pass


class ExplicitSelectionSpec(SelectionSpec):
    """Selection specification for explicit dataset selections.

    This mode represents a fully-specified list of dataset keys provided by the user.
    A full set of (site, variable, periodicity) must be provided.
    """

    def __init__(self, explicit: list[DatasetKey]):
        """Create an explicit selection specification.

        Args:
            explicit: List of explicitly selected dataset keys.
        """
        self.explicit = explicit

    def resolve(self) -> list[DatasetKey]:
        """Resolve explicit dataset keys into unique dimension lists.

        Returns:
           List of DatasetKey data objects, specifying which datasets to process
        """
        return self.explicit


class CrossProductSelectionSpec(SelectionSpec):
    """Selection specification for cross-product dataset selection.

    This mode allows the user to (optionally) specify one or more dataset dimensions (site, variable, periodicity).
    Any dimension left unspecified (None) is treated as unconstrained and should be expanded to all available values
    during downstream metadata fetches.
    """

    def __init__(
        self, sites: list[str] | None = None, variables: list[str] | None = None, periodicities: list[str] | None = None
    ):
        """Create a cross-product selection specification.

        Args:
            sites: List of site(s) to include.
            variables: List of variable(s) to include.
            periodicities: List of ISO 8601 duration string(s) of the periodicity of the datasets.
        """
        self.sites = sites
        self.variables = variables
        self.periodicities = periodicities

    def resolve(self) -> tuple[list[str], list[str], list[str]]:
        """Resolve cross-product constraints into dimension lists.

        Returns:
            Tuple of (sites, variables, periodicities)
        """
        sites = self.sites or []
        variables = self.variables or []
        periodicities = self.periodicities or []

        return sites, variables, periodicities


@dataclass(frozen=True)
class RunConfig:
    """Runtime configuration object for a processing run. This collects user intent, including dataset selection
    constraints and the temporal processing window. It serves as the boundary between CLI parsing and runtime execution.
    """

    network: str
    selection: SelectionSpec
    start_date: date
    end_date: date
