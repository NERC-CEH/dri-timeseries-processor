import re
from unittest import TestCase

from parameterized import parameterized

from metadata_manager.models.common import (
    SITE_ID_EXTRACT_REGEX,
    URI_ID_EXTRACT_REGEX,
    SERVICE_BASE_URI,
    build_column_query_parameter,
    build_periodicity_query_parameter,
    build_processing_query_parameter,
    build_site_query_parameter,
    build_timeseries_id_query_parameter,
    build_processing_config_timeseries_id_query_parameter,
    build_processing_config_type_query_parameter,
    build_view_query_parameter,
    get_property,
)


class TestUriIdExtractRegex(TestCase):
    @parameterized.expand(
        [
            ("simple", "http://example.com/parameter/simple", "simple"),
            ("with_hyphen", "http://example.com/parameter/single-hyphen", "single-hyphen"),
            ("with_multiple_hyphen", "http://example.com/parameter/multiple-hyphen-test", "multiple-hyphen-test"),
            ("with_underscore", "http://example.com/parameter/under_score", "under_score"),
            ("with_multiple_underscore", "http://example.com/parameter/multiple_under_score", "multiple_under_score"),
            ("hypen_underscore", "http://example.com/parameter/mix-hyphen_underscore", "mix-hyphen_underscore"),
            ("with_numbers", "http://example.com/parameter/g1", "g1"),
        ]
    )
    def test_parsing_success(self, _, string, expected):
        """Test that validation passes when string format meets the regex."""
        result = re.match(URI_ID_EXTRACT_REGEX, string).group(1)
        self.assertEqual(result, expected)

    @parameterized.expand(
        [
            ("not_a_url", "invalid-format-not-url"),
            ("empty_string", ""),
            ("no_name_after_slash", "http://example.com/parameter/"),
            ("special_character", "http://example.com/parameter/test&value"),
        ]
    )
    def test_parsing_none(self, _, string):
        """Test that no result matched when string format that fails the regex."""
        result = re.match(URI_ID_EXTRACT_REGEX, string)
        self.assertIsNone(result)


class TestSiteIdExtractRegex(TestCase):
    @parameterized.expand(
        [
            ("all_string", f"{SERVICE_BASE_URI}/id/site/cosmos-chimn", "chimn"),
            ("with_numbers", f"{SERVICE_BASE_URI}/id/site/cosmos-alic1", "alic1"),
        ]
    )
    def test_parsing_success(self, _, string, expected):
        """Test that validation passes when string format meets the regex."""
        result = re.match(SITE_ID_EXTRACT_REGEX, string).group(1)
        self.assertEqual(result, expected)

    @parameterized.expand(
        [
            ("not_a_url", "invalid-format-not-url"),
            ("empty_string", ""),
            ("no_name_after_slash", "http://example.com/id/site/"),
            ("special_character", "http://example.com/id/site/cosmos-test&site"),
            ("multiple_hyphens", "http://example.com/id/site/cosmos-test-site-id"),
            ("only_numbers", "http://example.com/id/site/12345"),
        ]
    )
    def test_parsing_none(self, _, string):
        """Test that no result matched when string format that fails the regex."""
        result = re.match(SITE_ID_EXTRACT_REGEX, string)
        self.assertIsNone(result)


class TestGetProperty(TestCase):
    """Test the get_property function."""

    def test_get_property_int_float_str(self) -> None:
        """Test extracting an int property"""
        key = "abc"

        expected = 123
        result = get_property(key, {key: expected})
        self.assertEqual(result, expected)

        expected = 123.4
        result = get_property(key, {key: expected})
        self.assertEqual(result, expected)

        expected = "123"
        result = get_property(key, {key: expected})
        self.assertEqual(result, expected)

    def test_get_property_list(self) -> None:
        """Test extracting a string property"""
        key = "abc"
        expected = "123"
        result = get_property(key, {key: [expected]})
        self.assertEqual(result, expected)

    def test_get_property_none(self) -> None:
        """Test trying to extract a None dictionary"""
        key = "abc"
        expected = None
        result = get_property(key, None)
        self.assertEqual(result, expected)

    def test_get_property_falsy_value(self) -> None:
        """Test extracting a falsy value"""
        key = "abc"

        expected = None
        result = get_property(key, {key: expected})
        self.assertEqual(result, expected)

        expected = ""
        result = get_property(key, {key: expected})
        self.assertEqual(result, expected)

        expected = 0
        result = get_property(key, {key: expected})
        self.assertEqual(result, expected)


class TestBuildSiteQueryParameter(TestCase):
    """Tests the build_site_query_parameter."""

    def test_multiple_sites(self) -> None:
        """Test string built with multiple sites"""
        sites = ["test1", "test2"]
        network = "cosmos"
        expected = [
            ("originatingSite", f"{SERVICE_BASE_URI}/id/site/cosmos-test1"),
            ("originatingSite", f"{SERVICE_BASE_URI}/id/site/cosmos-test2"),
        ]

        result = build_site_query_parameter(sites, network)

        assert result == expected

    def test_no_sites(self) -> None:
        """Test empty list if no sites."""
        sites = []
        network = "cosmos"
        expected = []

        result = build_site_query_parameter(sites, network)

        assert result == expected


class TestBuildPeriodicityQueryParameter(TestCase):
    """Tests the build_periodicity_query_parameter."""

    def test_multiple_periods(self) -> None:
        """Test string built with multiple periods"""
        periods = ["P2D", "PT30M"]
        expected = [("type.measure.aggregation.periodicity", "P2D"), ("type.measure.aggregation.periodicity", "PT30M")]

        result = build_periodicity_query_parameter(periods)

        assert result == expected

    def test_no_periods(self) -> None:
        """Test empty list if no periods."""
        periods = []
        expected = []

        result = build_periodicity_query_parameter(periods)

        assert result == expected


class TestBuildColumnsQueryParameter(TestCase):
    """Tests the build_column_query_parameter."""

    def test_multiple_columns(self) -> None:
        """Test string built with multiple column names"""
        columns = ["col1", "col2"]
        expected = [("sourceColumnName", "col1"), ("sourceColumnName", "col2")]

        result = build_column_query_parameter(columns)

        assert result == expected

    def test_no_columns(self) -> None:
        """Test empty list if no columns."""
        columns = []
        expected = []

        result = build_periodicity_query_parameter(columns)

        assert result == expected


class TestBuildProcessingQueryParameter(TestCase):
    """Tests the build_processing_query_parameter."""

    def test_processing_level(self) -> None:
        """Test string built with a processing level"""
        expected = [("type.processingLevel", f"{SERVICE_BASE_URI}/ref/common/processing-level/raw")]

        result = build_processing_query_parameter(level="raw")

        assert result == expected


class TestBuildViewQueryParameter(TestCase):
    """Tests the build_view_query_parameter."""

    def test_processing_level(self) -> None:
        """Test string built with a view"""
        expected = [("_view", "timeseries")]

        result = build_view_query_parameter(view="timeseries")

        assert result == expected


class TestBuildTimeSeriesIDQueryParameter(TestCase):
    """Tests the build_timeseries_id_query_parameter."""

    def test_multiple_timeseries_ids(self) -> None:
        """Test string built with multiple timeseries ids"""
        ts_ids = ["ts_id_1", "ts_id_2"]
        expected = [("@id", "ts_id_1"), ("@id", "ts_id_2")]

        result = build_timeseries_id_query_parameter(ts_ids)

        assert result == expected


class TestBuildProcessingConfigTimeseriesIDQueryParameter(TestCase):
    """Tests the build_processing_config_timeseries_id_query_parameter."""

    def test_multiple_timeseries_ids(self) -> None:
        """Test string built with multiple timeseries ids"""
        ts_ids = ["ts_id_1", "ts_id_2"]
        expected = [("appliesToTimeSeries", "ts_id_1"), ("appliesToTimeSeries", "ts_id_2")]

        result = build_processing_config_timeseries_id_query_parameter(ts_ids)

        assert result == expected


class TestBuildProcessingConfigTypeQueryParameter(TestCase):
    """Tests the build_processing_config_type_query_parameter."""

    def test_processing_config_type(self) -> None:
        """Test string built with a processing config type"""
        config_type = "test-config-type"
        expected = [("type", f"{SERVICE_BASE_URI}/ref/common/configuration-type/{config_type}")]

        result = build_processing_config_type_query_parameter(config_type)

        assert result == expected
