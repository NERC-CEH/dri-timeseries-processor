import polars as pl
import unittest

from datetime import date, timedelta
from freezegun import freeze_time
from dritimeseriesprocessor import parser
from parameterized import  parameterized


class TestParseArgs(unittest.TestCase):
    """Test the parser instance is correctly instantiated."""

    def test_instance_created(self):
        args = parser.parse_args(['P1D', """--end_date=2024-03-10"""])
        assert args.period == 'P1D'
        assert args.end_date == '2024-03-10'

    @freeze_time("2024-09-19")
    def test_no_end_date(self):
        """Test end_date is todays date (mocked) by default."""
        args = parser.parse_args(['P1D'])
        assert args.period == 'P1D'
        assert args.end_date == '2024-09-19'

    def test_no_period(self):
        with self.assertRaises(SystemExit):
            parser.parse_args(["--end_date=2024-03-10"])

    def test_incorrect_argument_name(self):
        with self.assertRaises(SystemExit):
            parser.parse_args(['P1D', "--wrong_name=2024-03-10"])

class TestBuildDateRange(unittest.TestCase):
    """Test the build_date_range function.
    
    Note: Using 'prod' as the environment so we bypass the temp code and actually
    test the functionality once real sensor data is available.
    """

    @parameterized.expand(
        [
            ('P2D', "2024-11-03", "prod", (date(2024, 11, 1), date(2024, 11, 3))),
            ('P1M', "2024-11-03", "prod", (date(2024, 10, 3), date(2024, 11, 3))),
            ('P1M2W3D', "2024-11-03", "prod", (date(2024, 9, 16), date(2024, 11, 3)))
        ]
    )
    def test_valid_inputs(self, period, end_date, environment, expected):
        result = parser.build_date_range(period, end_date, environment)

        assert result == expected


class TestValidatePeriod(unittest.TestCase):
    """Test the validate_period function."""

    @parameterized.expand(
        [
            ('P1D', date(2024, 10, 10), timedelta(days=1)),
            ('P1W', date(2024, 10, 10), timedelta(days=7)),
            ('P1Y6M14D', date(2024, 10, 10), timedelta(days=563))
        ]
    )
    def test_valid_periods(self, period, end_date, expected):
        result = parser.validate_period(period, end_date)

        assert result == expected
    
    def test_time_component(self):
        with self.assertRaises(ValueError) as exc:
            parser.validate_period('P1DT6H', date(2024, 10, 10))
        
        self.assertEqual(str(exc.exception), "Period should not have a time component")

    def test_incorrect_period_format(self):
        with self.assertRaises(ValueError) as exc:
            parser.validate_period('rudolph', date(2024, 10, 10))
        
        self.assertEqual(
            str(exc.exception),
            """Incorrect period format. Should be a valid ISO8601 duration containing a combination of days,
            months or years e.g. P3Y6M4D or P3Y12W3D"""
        )

class TestValidateEndDate(unittest.TestCase):
    """Test the validate_end_datefunction."""

    def test_correct_format(self):
        result = parser.validate_end_date('2024-01-01')

        assert result == date(2024, 1, 1)
    
    @parameterized.expand(
        [
            ('santa'),
            ('2024/01/01'),
            ('01-31-2023')
        ]
    )
    def test_incorrect_format(self, end_date):
        with self.assertRaises(ValueError) as exc:
            parser.validate_end_date(end_date)

        self.assertEqual(
            str(exc.exception),
            "Incorrect date format, should be YYYY-MM-DD"""
        )