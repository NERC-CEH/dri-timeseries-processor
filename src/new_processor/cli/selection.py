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


@dataclass(frozen=True)
class RootQuery:
    """Identifier for a dataset dimension combination."""

    sites: list[str] | None = None
    variables: list[str] | None = None
    periodicities: list[str] | None = None

    def __repr__(self) -> str:
        return (
            "RootQuery("
            f"sites={self._fmt_dim(self.sites)} | "
            f"variables={self._fmt_dim(self.variables)} | "
            f"periodicities={self._fmt_dim(self.periodicities)}"
            ")"
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


class SelectionSpec(ABC):
    """Abstract base class for dataset selection specifications - capturing user intent regarding which datasets
    should be processed.
    """

    def __init__(self):
        # Use set to make sure we don't have duplicates
        self._root_queries = list(set(self._resolve()))

    @property
    def root_queries(self) -> list[RootQuery]:
        """The root queries of the selection specification"""
        return self._root_queries

    @abstractmethod
    def _resolve(self) -> list[RootQuery]:
        """Resolve the selection specification into concrete constraints.

        Returns:
            A tuple of (sites, variables, periodicities). Empty lists indicate unconstrained dimensions and should
            be interpreted as "all" by downstream components.
        """
        pass

    def __repr__(self) -> str:
        lines = []
        for query in self.root_queries:
            lines.append(f"- {query}")
        return f"SelectionSpec(\n{'\n'.join(lines)} \n)"


class ExplicitSelectionSpec(SelectionSpec):
    """Selection specification for explicit dataset selections.

    This mode represents a fully-specified list of dataset keys provided by the user.
    A full set of (site, variable, periodicity) must be provided.
    """

    def __init__(self, explicit: list[RootQuery]):
        """Create an explicit selection specification.

        Args:
            explicit: List of explicitly selected dataset keys.
        """
        self.explicit = explicit
        super().__init__()

    def _resolve(self) -> list[RootQuery]:
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
        super().__init__()

    def _resolve(self) -> list[RootQuery]:
        """Resolve cross-product constraints into dimensions.

        Returns:
            List of one DatasetKey data object, specifying which cross-product datasets to process
        """
        return [
            RootQuery(
                sites=self.sites,
                variables=self.variables,
                periodicities=self.periodicities,
            )
        ]


@dataclass(frozen=True)
class RunConfig:
    """Runtime configuration object for a processing run. This collects user intent, including dataset selection
    constraints and the temporal processing window. It serves as the boundary between CLI parsing and runtime execution.
    """

    network: str
    selection: SelectionSpec
    start_date: date
    end_date: date
