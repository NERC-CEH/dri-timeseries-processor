import unittest

from datetime import date, timedelta
from freezegun import freeze_time
from dritimeseriesprocessor import parser
from parameterized import  parameterized


class TestParseArgs(unittest.TestCase):
    """Test the parser instance is correctly instantiated."""

    def test_instance_created(self):
        args = parser.parse_args(['P1D', """--end_date=2024-03-10""", """--sites=alic1,bunny""", """--columns=TA,PA""", """--periodicity=PT30M"""])
        assert args.period == 'P1D'
        assert args.end_date == '2024-03-10'
        assert args.sites == 'alic1,bunny'
        assert args.periodicity == 'PT30M'
        assert args.columns == 'TA,PA'

    @freeze_time("2024-09-19")
    def test_no_end_date(self):
        """Test end_date is todays date (mocked) by default."""
        args = parser.parse_args(['P1D'])
        assert args.period == 'P1D'
        assert args.end_date == '2024-09-19'

    def test_no_sites(self):
        """Test site is None by default."""
        args = parser.parse_args(['P1D'])
        assert args.period == 'P1D'
        assert args.sites == None

    def test_no_periodicity(self):
        """Test period is None by default."""
        args = parser.parse_args(['P1D'])
        assert args.period == 'P1D'
        assert args.periodicity == None

    def test_no_columns(self):
        """Test columns is None by default."""
        args = parser.parse_args(['P1D'])
        assert args.period == 'P1D'
        assert args.columns == None

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

class TestValidateSites(unittest.TestCase):
    """Test the validate_sites function."""

    @parameterized.expand(
        [
            ('ALIC1', ['ALIC1', 'BUNNY', 'BALRD'], ['ALIC1']),
            ('ALIC1,BUNNY', ['ALIC1', 'BUNNY', 'BALRD'], ['ALIC1', 'BUNNY']),
            ('bunny', ['ALIC1', 'BUNNY', 'BALRD'], ['BUNNY']),
            ('buNnY,BALrd', ['ALIC1', 'BUNNY', 'BALRD'], ['BUNNY', 'BALRD']),
            (None, ['ALIC1', 'BUNNY', 'BALRD'], [])
        ]
    )
    def test_correct_sites_argument(self, sites, metadata_sites, expected):
        """Test correct formatted arguments return the right sites."""

        result = parser.validate_sites(sites, metadata_sites)

        self.assertEqual(sorted(result), sorted(expected))
    
    @parameterized.expand(
        [
            ('ALIC1, BUNNY', "Site  BUNNY should only contain letters and numbers."),
            ('BU!!Y', "Site BU!!Y should only contain letters and numbers."),
            ('ALIC1/BUNNY', "Site ALIC1/BUNNY should only contain letters and numbers."),
        ]
    )
    def test_incorrect_sites_argument(self, sites, error_message):
        """Test incorrectly formatted arguments raise Value Errors."""
        metadata_sites = ['some_sample_sites']

        with self.assertRaises(ValueError) as err:
            parser.validate_sites(sites, metadata_sites)

        self.assertEqual(str(err.exception), error_message)


class TestValidatePeriodicity(unittest.TestCase):
    """Test the validate_periodicity function."""

    @parameterized.expand(
        [
            ('P2D', ['P2D']),
            ('PT30M,P2D', ['PT30M', 'P2D']),
            ('pt30M,P2d', ['PT30M', 'P2D']),
            (None, [])
        ]
    )
    def test_correct_period_argument(self, periods, expected):
        """Test correct formatted arguments return the right periods."""

        result = parser.validate_periodicity(periods)

        self.assertEqual(result, expected)
    

    def test_incorrect_periods_argument(self):
        """Test incorrectly formatted arguments raise Value Errors."""
        period = "rubbish"
        error_message = f"Illegal ISO 8601 duration: {period.upper()}"

        with self.assertRaises(ValueError) as err:
            parser.validate_periodicity(period)

        self.assertEqual(str(err.exception), error_message)


class TestValidateColNames(unittest.TestCase):
    """Test the validate_columns function."""

    @parameterized.expand(
        [
            ('TA,PA', ['TA', 'PA']),
            ('T_A,PA_', ['T_A', 'PA_']),
            ('TA,PA', ['TA', 'PA']),
            ('ta,PA', ['TA', 'PA']),
            ('Ta,pA', ['TA', 'PA']),
            (None, [])
        ]
    )
    def test_correct_columns(self, columns, expected):
        """Test correct formatted arguments return the right column names."""
        result = parser.validate_columns(columns)

        self.assertEqual(result, expected)
    
    @parameterized.expand(
        [
            ('T!,PA', "Column T! should only contain letters, numbers and underscores."),
            ('TA,PA,TA', "Column TA is duplicated in the arguments."),
            ('TA, PA', "Column  PA should only contain letters, numbers and underscores.")
        ]
    )
    def test_incorrect_columns(self, columns, error_message):
        """Test incorrectly formatted arguments raise Value Errors."""
        with self.assertRaises(ValueError) as err:
            parser.validate_columns(columns)

        self.assertEqual(str(err.exception), error_message)
