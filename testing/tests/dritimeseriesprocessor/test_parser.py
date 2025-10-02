from datetime import date, timedelta

import pytest
import time_stream as ts
from freezegun import freeze_time

from dritimeseriesprocessor import parser


class TestParseArgs:
    """Test the parser instance is correctly instantiated."""

    def test_instance_created(self) -> None:
        args = parser.parse_args(
            [
                """--period=P1D""",
                """--end_date=2024-03-10""",
                """--sites=alic1,bunny""",
                """--columns=TA,PA""",
                """--periodicity=PT30M""",
                """--network=cosmos""",
            ]
        )
        assert args.network == "cosmos"
        assert args.period == "P1D"
        assert args.end_date == "2024-03-10"
        assert args.sites == "alic1,bunny"
        assert args.periodicity == "PT30M"
        assert args.columns == "TA,PA"

    @freeze_time("2024-09-19")
    def test_no_end_date(self) -> None:
        """Test end_date is todays date (mocked) by default."""
        args = parser.parse_args(["--network=cosmos", "--period=P1D"])
        assert args.period == "P1D"
        assert args.end_date == "2024-09-19"

    def test_no_sites(self) -> None:
        """Test site is None by default."""
        args = parser.parse_args(["--network=cosmos", "--period=P1D"])
        assert args.period == "P1D"
        assert args.sites is None

    def test_no_periodicity(self) -> None:
        """Test period is None by default."""
        args = parser.parse_args(["--network=cosmos", "--period=P1D"])
        assert args.period == "P1D"
        assert args.periodicity is None

    def test_no_columns(self) -> None:
        """Test columns is None by default."""
        args = parser.parse_args(["--network=cosmos", "--period=P1D"])
        assert args.period == "P1D"
        assert args.columns is None

    def test_no_period(self) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args(["--network=cosmos --end_date=2024-03-10"])

    def test_incorrect_argument_name(self) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args(["--network=cosmos --period=P1D", "--wrong_name=2024-03-10"])


class TestBuildDateRange:
    """Test the build_date_range function.

    Note: Using 'prod' as the environment so we bypass the temp code and actually
    test the functionality once real sensor data is available.
    """

    @pytest.mark.parametrize(
        "period,end_date,environment,expected",
        [
            ("P2D", "2024-11-03", "prod", (date(2024, 11, 1), date(2024, 11, 3))),
            ("P1M", "2024-11-03", "prod", (date(2024, 10, 3), date(2024, 11, 3))),
            ("P1M2W3D", "2024-11-03", "prod", (date(2024, 9, 16), date(2024, 11, 3))),
        ],
    )
    def test_valid_inputs(self, period: str, end_date: str, environment: str, expected: tuple[date, date]) -> None:
        result = parser.build_date_range(period, end_date, environment)

        assert result == expected


class TestValidatePeriod:
    """Test the validate_period function."""

    @pytest.mark.parametrize(
        "period,end_date,expected",
        [
            ("P1D", date(2024, 10, 10), timedelta(days=1)),
            ("P1W", date(2024, 10, 10), timedelta(days=7)),
            ("P1Y6M14D", date(2024, 10, 10), timedelta(days=563)),
        ],
    )
    def test_valid_periods(self, period: str, end_date: date, expected: timedelta) -> None:
        result = parser.validate_period(period, end_date)

        assert result == expected

    def test_time_component(self) -> None:
        with pytest.raises(ValueError, match="Period should not have a time component"):
            parser.validate_period("P1DT6H", date(2024, 10, 10))

    def test_incorrect_period_format(self) -> None:
        expected_error = "Incorrect period format. Should be a valid ISO8601 duration containing a combination of days"
        with pytest.raises(ValueError, match=expected_error):
            parser.validate_period("rudolph", date(2024, 10, 10))


class TestValidateEndDate:
    """Test the validate_end_datefunction."""

    def test_correct_format(self) -> None:
        result = parser.validate_end_date("2024-01-01")

        assert result == date(2024, 1, 1)

    @pytest.mark.parametrize("end_date", [("santa"), ("2024/01/01"), ("01-31-2023")])
    def test_incorrect_format(self, end_date: str) -> None:
        with pytest.raises(ValueError, match="Incorrect date format, should be YYYY-MM-DD"):
            parser.validate_end_date(end_date)


class TestValidateSites:
    """Test the validate_sites function."""

    @pytest.mark.parametrize(
        "sites,metadata_sites,expected",
        [
            ("ALIC1", ["ALIC1", "BUNNY", "BALRD"], ["ALIC1"]),
            ("ALIC1,BUNNY", ["ALIC1", "BUNNY", "BALRD"], ["ALIC1", "BUNNY"]),
            ("bunny", ["ALIC1", "BUNNY", "BALRD"], ["BUNNY"]),
            ("buNnY,BALrd", ["ALIC1", "BUNNY", "BALRD"], ["BUNNY", "BALRD"]),
            (None, ["ALIC1", "BUNNY", "BALRD"], []),
        ],
    )
    def test_correct_sites_argument(self, sites: list[str], metadata_sites: list[str], expected: list[str]) -> None:
        """Test correct formatted arguments return the right sites."""

        result = parser.validate_sites(sites, metadata_sites)

        assert sorted(result) == sorted(expected)

    @pytest.mark.parametrize(
        "sites,error_message",
        [
            ("ALIC1, BUNNY", "Site  BUNNY should only contain letters and numbers."),
            ("BU!!Y", "Site BU!!Y should only contain letters and numbers."),
            ("ALIC1/BUNNY", "Site ALIC1/BUNNY should only contain letters and numbers."),
        ],
    )
    def test_incorrect_sites_argument(self, sites: list[str], error_message: str) -> None:
        """Test incorrectly formatted arguments raise Value Errors."""
        metadata_sites = ["some_sample_sites"]

        with pytest.raises(ValueError, match=error_message):
            parser.validate_sites(sites, metadata_sites)


class TestValidatePeriodicity:
    """Test the validate_periodicity function."""

    @pytest.mark.parametrize(
        "periods,expected",
        [("P2D", ["P2D"]), ("PT30M,P2D", ["PT30M", "P2D"]), ("pt30M,P2d", ["PT30M", "P2D"]), (None, [])],
    )
    def test_correct_period_argument(self, periods: str, expected: list[str]) -> None:
        """Test correct formatted arguments return the right periods."""

        result = parser.validate_periodicity(periods)

        assert result == expected

    def test_incorrect_periods_argument(self) -> None:
        """Test incorrectly formatted arguments raise Value Errors."""
        period = "rubbish"
        error_message = f"Illegal ISO 8601 duration: {period.upper()}"

        with pytest.raises(ts.exceptions.PeriodParsingError, match=error_message):
            parser.validate_periodicity(period)


class TestValidateColNames:
    """Test the validate_columns function."""

    @pytest.mark.parametrize(
        "columns,expected",
        [
            ("TA,PA", ["TA", "PA"]),
            ("T_A,PA_", ["T_A", "PA_"]),
            ("TA,PA", ["TA", "PA"]),
            ("ta,PA", ["TA", "PA"]),
            ("Ta,pA", ["TA", "PA"]),
            (None, []),
        ],
    )
    def test_correct_columns(self, columns: str, expected: list[str]) -> None:
        """Test correct formatted arguments return the right column names."""
        result = parser.validate_columns(columns)

        assert result == expected

    @pytest.mark.parametrize(
        "columns,error_message",
        [
            ("T!,PA", "Column T! should only contain letters, numbers and underscores."),
            ("TA,PA,TA", "Column TA is duplicated in the arguments."),
            ("TA, PA", "Column  PA should only contain letters, numbers and underscores."),
        ],
    )
    def test_incorrect_columns(self, columns: str, error_message: str) -> None:
        """Test incorrectly formatted arguments raise Value Errors."""
        with pytest.raises(ValueError, match=error_message):
            parser.validate_columns(columns)
