from dataclasses import dataclass

from new_processor.cli.models import SelectionSpec


@dataclass(frozen=True)
class DatasetKey:
    site: str
    column: str
    periodicity: str


class SelectionResolver:
    def resolve(self, spec: SelectionSpec) -> list[DatasetKey]:
        if spec.explicit is not None:
            return self._resolve_explicit(spec)

        return self._resolve_cross_product(spec)

    def _resolve_explicit(self, spec: SelectionSpec) -> list[DatasetKey]:
        return [
            DatasetKey(
                site=e.site,
                column=e.column,
                periodicity=e.periodicity,
            )
            for e in spec.explicit
        ]

    def _resolve_cross_product(self, spec: SelectionSpec) -> list[DatasetKey]:
        return [
            DatasetKey(
                site=site,
                column=column,
                periodicity=periodicity,
            )
            for site in spec.sites
            for column in spec.columns
            for periodicity in spec.periodicities
        ]
