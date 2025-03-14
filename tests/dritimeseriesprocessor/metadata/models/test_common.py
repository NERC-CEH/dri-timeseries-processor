import re
from unittest import TestCase

from parameterized import parameterized

from dritimeseriesprocessor.metadata.models.common import SITE_ID_EXTRACT_REGEX, URI_ID_EXTRACT_REGEX


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