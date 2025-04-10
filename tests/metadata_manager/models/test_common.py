import re
from unittest import TestCase

from parameterized import parameterized

from metadata_manager.models.common import (
    SITE_ID_EXTRACT_REGEX, URI_ID_EXTRACT_REGEX,
    get_property,
    build_site_query_parameter,
    build_periodicity_query_parameter,
    build_column_query_parameter
)

class TestUriIdExtractRegex(TestCase):
    @parameterized.expand([
        ("simple", "http://example.com/parameter/simple", "simple"),
        ("with_hyphen", "http://example.com/parameter/single-hyphen", "single-hyphen"),
        ("with_multiple_hyphen", "http://example.com/parameter/multiple-hyphen-test", "multiple-hyphen-test"),
        ("with_underscore", "http://example.com/parameter/under_score", "under_score"),
        ("with_multiple_underscore", "http://example.com/parameter/multiple_under_score", "multiple_under_score"),
        ("hypen_underscore", "http://example.com/parameter/mix-hyphen_underscore", "mix-hyphen_underscore"),
        ("with_numbers", "http://example.com/parameter/g1", "g1")
    ])
    def test_parsing_success(self, _, string, expected):
        """Test that validation passes when string format meets the regex."""
        result = re.match(URI_ID_EXTRACT_REGEX, string).group(1)
        self.assertEqual(result, expected)

    @parameterized.expand([
        ("not_a_url", "invalid-format-not-url"),
        ("empty_string", ""),
        ("no_name_after_slash", "http://example.com/parameter/"),
        ("special_character", "http://example.com/parameter/test&value"),
    ])
    def test_parsing_none(self, _, string):
        """Test that no result matched when string format that fails the regex."""
        result = re.match(URI_ID_EXTRACT_REGEX, string)
        self.assertIsNone(result)


class TestSiteIdExtractRegex(TestCase):
    @parameterized.expand([
        ("all_string", "http://fdri.ceh.ac.uk/id/site/cosmos-chimn", "chimn"),
        ("with_numbers", "http://fdri.ceh.ac.uk/id/site/cosmos-alic1", "alic1"),
    ])
    def test_parsing_success(self, _, string, expected):
        """Test that validation passes when string format meets the regex."""
        result = re.match(SITE_ID_EXTRACT_REGEX, string).group(1)
        self.assertEqual(result, expected)

    @parameterized.expand([
        ("not_a_url", "invalid-format-not-url"),
        ("empty_string", ""),
        ("no_name_after_slash", "http://example.com/id/site/"),
        ("special_character", "http://example.com/id/site/cosmos-test&site"),
        ("multiple_hyphens", "http://example.com/id/site/cosmos-test-site-id"),
        ("only_numbers", "http://example.com/id/site/12345")
    ])
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
        sites =["test1", "test2"]
        expected = [('originatingSite', f"http://fdri.ceh.ac.uk/id/site/cosmos-test1"),
                    ('originatingSite', f"http://fdri.ceh.ac.uk/id/site/cosmos-test2")]
        
        result = build_site_query_parameter(sites)

        assert result == expected

class TestBuildPeriodicityQueryParameter(TestCase):
    """Tests the build_periodicity_query_parameter."""

    def test_multiple_periods(self) -> None:
        """Test string built with multiple periods"""
        periods = ["P2D", "PT30M"]
        expected = [("type.measure.aggregation.periodicity", "P2D"),
                    ("type.measure.aggregation.periodicity", "PT30M")]
        
        result = build_periodicity_query_parameter(periods)

        assert result == expected

    def test_no_periods(self) -> None:
        """Test empty list if no period."""
        periods = None
        expected = []
        
        result = build_periodicity_query_parameter(periods)

        assert result == expected

class TestBuildColumnsQueryParameter(TestCase):
    """Tests the build_column_query_parameter."""

    def test_multiple_columns(self) -> None:
        """Test string built with multiple column names"""
        columns = ["col1", "col2"]
        expected = [('sourceColumnName', 'col1'), ('sourceColumnName', 'col2')]
        
        result = build_column_query_parameter(columns)

        assert result == expected
