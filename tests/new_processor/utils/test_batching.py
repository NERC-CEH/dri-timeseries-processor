from new_processor.utils.batching import batched


class TestBatched:
    def test_exact_multiple(self) -> None:
        result = batched([1, 2, 3, 4], size=2)
        assert result == [[1, 2], [3, 4]]

    def test_non_exact_multiple(self) -> None:
        result = batched([1, 2, 3, 4, 5], size=2)
        assert result == [[1, 2], [3, 4], [5]]

    def test_size_larger_than_iterable(self) -> None:
        result = batched([1, 2, 3], size=10)
        assert result == [[1, 2, 3]]

    def test_size_one(self) -> None:
        result = batched([1, 2, 3], size=1)
        assert result == [[1], [2], [3]]

    def test_empty_iterable(self) -> None:
        result = batched([], size=3)
        assert result == []

    def test_single_element(self) -> None:
        result = batched([1], size=3)
        assert result == [[1]]

    def test_accepts_any_iterable(self) -> None:
        data = (i for i in range(5))  # generator
        result = batched(data, size=2)
        assert result == [[0, 1], [2, 3], [4]]
