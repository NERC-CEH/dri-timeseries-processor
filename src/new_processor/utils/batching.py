from collections.abc import Iterable
from typing import TypeVar

T = TypeVar("T")


def batched(iterable: Iterable[T], size: int) -> list[list[T]]:
    """Split an iterable into fixed-size batches."""
    batch: list[T] = []
    batches: list[list[T]] = []

    for item in iterable:
        batch.append(item)
        if len(batch) == size:
            batches.append(batch)
            batch = []

    if batch:
        batches.append(batch)

    return batches
