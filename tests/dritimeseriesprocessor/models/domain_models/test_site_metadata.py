from datetime import datetime

import pytest

from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata


def make_site(start_date: datetime, end_date: datetime | None = None) -> SiteMetadata:
    return SiteMetadata(site_id="test-site", network="cosmos", start_date=start_date, end_date=end_date)


START = datetime(2024, 1, 1)
END = datetime(2025, 1, 1)


class TestIsActive:
    @pytest.mark.parametrize(
        "site, window_start, window_end, expected",
        [
            # Active cases
            pytest.param(make_site(datetime(2020, 1, 1)), START, END, True, id="active_within_window"),
            pytest.param(make_site(datetime(2000, 1, 1)), START, END, True, id="no_end_date"),
            pytest.param(
                make_site(datetime(2020, 1, 1), datetime(2024, 6, 1)), START, END, True, id="overlaps_window_start"
            ),
            pytest.param(make_site(datetime(2024, 6, 1)), START, END, True, id="overlaps_window_end"),
            # Inactive cases
            pytest.param(make_site(datetime(2026, 1, 1)), START, END, False, id="site_starts_after_window_end"),
            pytest.param(make_site(datetime(2025, 1, 1)), START, END, False, id="site_starts_exactly_at_window_end"),
            pytest.param(
                make_site(datetime(2000, 1, 1), datetime(2023, 1, 1)),
                START,
                END,
                False,
                id="site_ends_before_window_start",
            ),
            pytest.param(
                make_site(datetime(2000, 1, 1), datetime(2024, 1, 1)),
                START,
                END,
                False,
                id="site_ends_exactly_at_window_start",
            ),
            # None window bounds
            pytest.param(
                make_site(datetime(2000, 1, 1), datetime(2020, 1, 1)),
                None,
                END,
                True,
                id="no_window_start_ignores_site_end_date",
            ),
            pytest.param(
                make_site(datetime(2030, 1, 1)), START, None, True, id="no_window_end_ignores_site_start_date"
            ),
            pytest.param(
                make_site(datetime(2000, 1, 1), datetime(2020, 1, 1)),
                None,
                None,
                True,
                id="no_window_bounds_always_active",
            ),
        ],
    )
    def test_is_active(
        self,
        site: SiteMetadata,
        window_start: datetime | None,
        window_end: datetime | None,
        expected: bool,
    ) -> None:
        assert site.is_active(window_start=window_start, window_end=window_end) == expected
