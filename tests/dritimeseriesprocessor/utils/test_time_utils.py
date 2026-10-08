from datetime import date, datetime

from dritimeseriesprocessor.utils.time_utils import split_into_calendar_years, to_datetime


class TestToDatetime:
    def test_date_is_converted_to_midnight_datetime(self) -> None:
        assert to_datetime(date(2024, 3, 15)) == datetime(2024, 3, 15, 0, 0, 0)


class TestSplitIntoCalendarYears:
    def test_single_year_range_gives_one_chunk(self) -> None:
        """Tests that a range within one year gives a single chunk covering exactly that range."""
        assert split_into_calendar_years(date(2020, 3, 5), date(2020, 9, 1)) == [
            (datetime(2020, 3, 5), datetime(2020, 9, 1))
        ]

    def test_multi_year_range_has_partial_first_and_last_chunks(self) -> None:
        """Tests that a multi-year range is split at year boundaries with no overlap between chunks."""
        assert split_into_calendar_years(date(2019, 6, 15), date(2021, 2, 10)) == [
            (datetime(2019, 6, 15), datetime(2019, 12, 31)),
            (datetime(2020, 1, 1), datetime(2020, 12, 31)),
            (datetime(2021, 1, 1), datetime(2021, 2, 10)),
        ]

    def test_start_equals_end_gives_one_day_chunk(self) -> None:
        """Tests that a range of a single day gives one chunk of that day."""
        assert split_into_calendar_years(date(2024, 2, 29), date(2024, 2, 29)) == [
            (datetime(2024, 2, 29), datetime(2024, 2, 29))
        ]

    def test_datetimes_are_treated_as_their_dates(self) -> None:
        """Tests that datetimes can be given, and their time of day is ignored."""
        assert split_into_calendar_years(datetime(2019, 12, 31, 18, 30), datetime(2020, 1, 1, 3, 0)) == [
            (datetime(2019, 12, 31), datetime(2019, 12, 31)),
            (datetime(2020, 1, 1), datetime(2020, 1, 1)),
        ]

    def test_end_before_start_gives_no_chunks(self) -> None:
        """Tests that a range ending before it starts gives no chunks."""
        assert split_into_calendar_years(date(2024, 5, 1), date(2024, 4, 1)) == []
