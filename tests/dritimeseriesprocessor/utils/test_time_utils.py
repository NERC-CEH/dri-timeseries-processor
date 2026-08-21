from datetime import date, datetime

from dritimeseriesprocessor.utils.time_utils import to_datetime


class TestToDatetime:
    def test_date_is_converted_to_midnight_datetime(self) -> None:
        assert to_datetime(date(2024, 3, 15)) == datetime(2024, 3, 15, 0, 0, 0)
