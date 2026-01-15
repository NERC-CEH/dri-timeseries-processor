from typing import Any

import pytest

from dritimeseriesprocessor.utils.strings import extract_uri_id


class TestExtractUriId:
    @pytest.mark.parametrize(
        "uri, expected",
        [
            ("", ""),
            ("/", ""),
            ("http://example.com", "example.com"),
            ("http://example.com/", "example.com"),
            ("http://example.com/resource", "resource"),
            ("http://example.com/resource/", "resource"),
            ("http://example.com/resource/123", "123"),
            ("https://api.example.com/v1/items/abc123/", "abc123"),
            ("no slashes", "no slashes"),
        ],
    )
    def test_extract_valid(self, uri: str, expected: str) -> None:
        result = extract_uri_id(uri)
        assert result == expected

    @pytest.mark.parametrize(
        "uri",
        [
            None,
            123,
            ["http://example.com/a/b"],
            {"uri": "http://example.com/a/b"},
        ],
    )
    def test_extract_invalid_type(self, uri: Any) -> None:
        """Test that non-string inputs raise an appropriate error."""
        with pytest.raises(ValueError):
            extract_uri_id(uri)  # type: ignore - expecting type warning
