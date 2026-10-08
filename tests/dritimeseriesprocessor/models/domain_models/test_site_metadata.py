from datetime import datetime

import pytest

from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata


def make_site(start_date: datetime, end_date: datetime | None = None) -> SiteMetadata:
    return SiteMetadata(site_id="test-site", network="cosmos", start_date=start_date, end_date=end_date)


FIRST_DAY = datetime(2024, 1, 1)
LAST_DAY = datetime(2025, 1, 1)


class TestIsActive:
    @pytest.mark.parametrize(
        "site, first_day, last_day, expected",
        [
            # Active cases
            pytest.param(make_site(datetime(2020, 1, 1)), FIRST_DAY, LAST_DAY, True, id="active_within_range"),
            pytest.param(
                make_site(datetime(2020, 1, 1), datetime(2024, 6, 1)),
                FIRST_DAY,
                LAST_DAY,
                True,
                id="overlaps_first_day",
            ),
            pytest.param(make_site(datetime(2024, 6, 1)), FIRST_DAY, LAST_DAY, True, id="overlaps_last_day"),
            pytest.param(make_site(datetime(2025, 1, 1)), FIRST_DAY, LAST_DAY, True, id="site_starts_on_last_day"),
            pytest.param(
                make_site(datetime(2025, 1, 1, 10, 30)), FIRST_DAY, LAST_DAY, True, id="site_starts_during_last_day"
            ),
            pytest.param(
                make_site(datetime(2000, 1, 1), datetime(2024, 1, 1, 9, 0)),
                FIRST_DAY,
                LAST_DAY,
                True,
                id="site_ends_during_first_day",
            ),
            pytest.param(
                make_site(datetime(2000, 1, 1), datetime(2024, 1, 1, 9, 0)),
                datetime(2024, 1, 1, 15, 0),
                LAST_DAY,
                True,
                id="time_of_day_on_first_day_is_ignored",
            ),
            # Inactive cases
            pytest.param(
                make_site(datetime(2025, 1, 2)), FIRST_DAY, LAST_DAY, False, id="site_starts_day_after_last_day"
            ),
            pytest.param(
                make_site(datetime(2000, 1, 1), datetime(2023, 1, 1)),
                FIRST_DAY,
                LAST_DAY,
                False,
                id="site_ends_before_first_day",
            ),
            pytest.param(
                make_site(datetime(2000, 1, 1), datetime(2024, 1, 1)),
                FIRST_DAY,
                LAST_DAY,
                False,
                id="site_ends_at_the_start_of_first_day",
            ),
            # Missing days
            pytest.param(
                make_site(datetime(2000, 1, 1), datetime(2020, 1, 1)),
                None,
                LAST_DAY,
                True,
                id="no_first_day_ignores_site_end_date",
            ),
            pytest.param(
                make_site(datetime(2030, 1, 1)), FIRST_DAY, None, True, id="no_last_day_ignores_site_start_date"
            ),
            pytest.param(
                make_site(datetime(2000, 1, 1), datetime(2020, 1, 1)),
                None,
                None,
                True,
                id="no_days_always_active",
            ),
        ],
    )
    def test_is_active(
        self,
        site: SiteMetadata,
        first_day: datetime | None,
        last_day: datetime | None,
        expected: bool,
    ) -> None:
        """Tests that a site is active if it was open at any time from the first day to the end of the last."""
        assert site.is_active(first_day, last_day) == expected
