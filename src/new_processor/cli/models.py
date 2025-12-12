from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ExplicitSelection:
    site: str
    column: str
    periodicity: str


@dataclass(frozen=True)
class SelectionSpec:
    """Either explicit selections OR cross-product selectors."""

    explicit: list[ExplicitSelection] | None = None
    sites: list[str] | None = None
    columns: list[str] | None = None
    periodicities: list[str] | None = None

    def mode(self) -> str:
        return "explicit" if self.explicit else "cross_product"


@dataclass(frozen=True)
class RunConfig:
    network: str
    selection: SelectionSpec
    start_date: date
    end_date: date
