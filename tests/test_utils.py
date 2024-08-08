import unittest

from dritimeseriesprocessor.utils import remove_protocol_from_url, validate_iso8601_duration


class TestValidateISO8601Duration(unittest.TestCase):
    def test_valid_duration_full_format(self):
        """Test a valid ISO 8601 duration in full format."""
        duration = "P1Y2M3DT4H5M6S"
        self.assertTrue(validate_iso8601_duration(duration))

    def test_valid_duration_days_only(self):
        """Test a valid ISO 8601 duration with days only."""
        duration = "P3D"
        self.assertTrue(validate_iso8601_duration(duration))

    def test_valid_duration_hours_only(self):
        """Test a valid ISO 8601 duration with hours only."""
        duration = "PT4H"
        self.assertTrue(validate_iso8601_duration(duration))

    def test_valid_duration_combination(self):
        """Test a valid ISO 8601 duration with a combination of elements."""
        duration = "P2W"
        self.assertTrue(validate_iso8601_duration(duration))

    def test_invalid_duration_missing_p(self):
        """Test an invalid ISO 8601 duration missing the 'P' character."""
        duration = "1Y2M3DT4H5M6S"
        self.assertFalse(validate_iso8601_duration(duration))

    def test_invalid_duration_wrong_format(self):
        """Test an invalid ISO 8601 duration with a wrong format."""
        duration = "P1Y2M3D4H5M6S"
        self.assertFalse(validate_iso8601_duration(duration))

    def test_invalid_duration_non_iso_string(self):
        """Test an invalid ISO 8601 duration with a non-ISO string."""
        duration = "This is not a duration"
        self.assertFalse(validate_iso8601_duration(duration))

    def test_empty_string(self):
        """Test an invalid ISO 8601 duration with an empty string."""
        duration = ""
        self.assertFalse(validate_iso8601_duration(duration))


class TestRemoveProtocolFromUrl(unittest.TestCase):
    def test_https_url(self):
        """Test removing protocol from an HTTPS URL."""
        url = "https://www.example.com"
        expected = "www.example.com"
        result = remove_protocol_from_url(url)
        self.assertEqual(result, expected)

    def test_http_url(self):
        """Test removing protocol from an HTTP URL."""
        url = "http://www.example.com"
        expected = "www.example.com"
        result = remove_protocol_from_url(url)
        self.assertEqual(result, expected)

    def test_url_with_path(self):
        """Test removing protocol from a URL with a path."""
        url = "https://www.example.com/path/to/resource"
        expected = "www.example.com/path/to/resource"
        result = remove_protocol_from_url(url)
        self.assertEqual(result, expected)

    def test_url_with_port(self):
        """Test removing protocol from a URL with a port."""
        url = "https://www.example.com:8080"
        expected = "www.example.com:8080"
        result = remove_protocol_from_url(url)
        self.assertEqual(result, expected)

    def test_url_without_protocol(self):
        """Test a URL that already has no protocol."""
        url = "www.example.com"
        expected = "www.example.com"
        result = remove_protocol_from_url(url)
        self.assertEqual(result, expected)
