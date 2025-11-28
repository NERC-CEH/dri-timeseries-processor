import pytest

from new_processor.utils.urls import remove_protocol_from_url


class TestRemoveProtocolFromUrl:
    @pytest.mark.parametrize(
        "url, expected",
        [
            ("https://www.example.com", "www.example.com"),
            ("http://fdri.ceh.ac.uk/ref", "fdri.ceh.ac.uk/ref"),
            ("http://fdri.ceh.ac.uk:9000/path/to/file", "fdri.ceh.ac.uk:9000/path/to/file"),
            ("https://example.com:443", "example.com:443"),
            ("https://example.com?query=1", "example.com?query=1"),
            ("https://example.com:1234/path?q=1#frag", "example.com:1234/path?q=1#frag"),
            ("ftp://weird.example.com/data", "weird.example.com/data"),
            ("example.com", "example.com"),
            ("example.com/path", "example.com/path"),
        ],
    )
    def test_valid_string(self, url: str, expected: str) -> None:
        assert remove_protocol_from_url(url) == expected

    def test_empty_string(self) -> None:
        assert remove_protocol_from_url("") == ""
