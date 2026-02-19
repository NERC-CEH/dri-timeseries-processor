import pytest

from dritimeseriesprocessor.models.domain_models.time_series_container import check_common_attributes
from dritimeseriesprocessor.utils.enums import ProcessingLevel
from utils.data_creation import make_time_series_container


class TestCheckCommonAttributes:
    def test_empty_containers_returns_none(self) -> None:
        assert check_common_attributes([], "a") is None
        assert check_common_attributes([], ["a", "b"]) is None

    containers = [
        make_time_series_container("a"),
        make_time_series_container("b"),
        make_time_series_container("c"),
    ]

    def test_single_attr(self) -> None:
        assert check_common_attributes(self.containers, "time_column_name") == "time"

    def test_multiple_attr(self) -> None:
        assert check_common_attributes(self.containers, ["time_column_name", "resolution", "processing_level"]) == [
            "time",
            "P1D",
            ProcessingLevel.PROCESSED,
        ]

    def test_single_attr_not_common(self) -> None:
        with pytest.raises(ValueError):
            check_common_attributes(self.containers, "ts_id")

    def test_multiple_attr_one_not_common(self) -> None:
        with pytest.raises(ValueError):
            check_common_attributes(self.containers, ["time_column_name", "resolution", "processing_level", "ts_id"])

    def test_multiple_attr_all_not_common(self) -> None:
        with pytest.raises(ValueError):
            check_common_attributes(self.containers, ["ts_id", "source_site", "source_column"])
