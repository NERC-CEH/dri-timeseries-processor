from datetime import date, datetime

from dritimeseriesprocessor.utils.time_utils import to_datetime, year_chunks


class TestToDatetime:
    def test_date_is_converted_to_midnight_datetime(self) -> None:
        assert to_datetime(date(2024, 3, 15)) == datetime(2024, 3, 15, 0, 0, 0)


class TestYearChunks:
    def test_range_within_a_single_year_returns_one_chunk(self) -> None:
        """A window that doesn't cross a calendar-year boundary shouldn't be split at all."""
        assert year_chunks(datetime(2024, 3, 15), datetime(2024, 9, 1)) == [
            (datetime(2024, 3, 15), datetime(2024, 9, 1)),
        ]

    def test_single_day_range_returns_one_chunk(self) -> None:
        assert year_chunks(datetime(2024, 1, 1), datetime(2024, 1, 1)) == [
            (datetime(2024, 1, 1), datetime(2024, 1, 1)),
        ]

    def test_range_spanning_multiple_years_is_split_at_year_boundaries(self) -> None:
        """Each chunk should cover a full calendar year, except the first and last which are clipped to the
        requested start and end dates.
        """
        assert year_chunks(datetime(2020, 3, 15), datetime(2023, 6, 1)) == [
            (datetime(2020, 3, 15), datetime(2020, 12, 31)),
            (datetime(2021, 1, 1), datetime(2021, 12, 31)),
            (datetime(2022, 1, 1), datetime(2022, 12, 31)),
            (datetime(2023, 1, 1), datetime(2023, 6, 1)),
        ]

    def test_range_exactly_spanning_one_calendar_year(self) -> None:
        assert year_chunks(datetime(2024, 1, 1), datetime(2024, 12, 31)) == [
            (datetime(2024, 1, 1), datetime(2024, 12, 31)),
        ]
