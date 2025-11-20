"""
Batch utilities for dependency graph resolution.

This module defines the Batch class, which manages iterative batches of time series datasets during dependency
graph construction. A batch represents the current set of unresolved datasets in the recursive dependency
resolution process.
"""

from new_processor.dag.repositories import DatasetRepository
from new_processor.domain_models.time_series_container import TimeSeriesContainer


class Batch:
    def __init__(self, initial: list[TimeSeriesContainer], dataset_repository: DatasetRepository):
        self.current = {ds.ts_id: ds for ds in initial}
        self.next = {}
        self.dataset_repository = dataset_repository

    def add_dependencies_to_next_batch(self, container: TimeSeriesContainer) -> None:
        """Add dataset dependencies into the next batch for resolution.

        For every dependency ID listed by the container (from metadata or configs):
            - If we haven't already processed or stored this dataset, fetch it from the API.
            - The fetched container is appended to the next batch for further resolution.

        Args:
            container: The dataset whose dependency IDs will be inspected.
        """
        for dep_id in container.all_dependencies():
            if not self.dataset_repository.is_resolved(dep_id) and dep_id not in self.next:
                dep_container = self.dataset_repository.fetch_dataset_by_id(dep_id)
                self.next[dep_id] = dep_container

    def advance(self) -> None:
        """Advance the current batch."""
        self.current = self.next
        self.next = {}

    def empty(self) -> bool:
        """Return whether the batch is empty or not."""
        return not self.current
