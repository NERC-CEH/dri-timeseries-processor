from abc import abstractmethod, ABC
from dataclasses import dataclass
from datetime import date

from new_processor.utils.enums import CliSelectionMode


@dataclass(frozen=True)
class DatasetKey:
    site: str | None = None
    variable: str | None = None
    periodicity: str | None = None


class SelectionSpec(ABC):
    def __init__(self, mode: CliSelectionMode):
        self.mode = mode

    @abstractmethod
    def resolve(self) -> tuple[list[str], list[str], list[str]]:
        pass


class ExplicitSelectionSpec(SelectionSpec):
    def __init__(self, explicit: list[DatasetKey]):
        super().__init__(CliSelectionMode.EXPLICIT)
        self.explicit = explicit

    def resolve(self) -> tuple[list[str], list[str], list[str]]:
        sites = sorted({key.site for key in self.explicit})
        variables = sorted({key.variable for key in self.explicit})
        periodicities = sorted({key.periodicity for key in self.explicit})

        return sites, variables, periodicities


class CrossProductSelectionSpec(SelectionSpec):
    def __init__(
        self, sites: list[str] | None = None, variables: list[str] | None = None, periodicities: list[str] | None = None
    ):
        super().__init__(CliSelectionMode.CROSS_PRODUCT)
        self.sites = sites
        self.variables = variables
        self.periodicities = periodicities

    def resolve(self) -> tuple[list[str], list[str], list[str]]:
        sites = self.sites or []
        variables = self.variables or []
        periodicities = self.periodicities or []

        return sites, variables, periodicities


@dataclass(frozen=True)
class RunConfig:
    network: str
    selection: SelectionSpec
    start_date: date
    end_date: date
