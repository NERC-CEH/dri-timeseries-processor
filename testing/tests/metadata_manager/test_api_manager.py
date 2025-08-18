import json
from unittest.async_case import IsolatedAsyncioTestCase
from unittest.mock import MagicMock, patch

from httpx import HTTPError, HTTPStatusError, Request, Response, TimeoutException

from metadata_manager.api_manager import MetadataAPIManager
from testing.utils.mock_metadata_api import MockMetadataAPI


class TestMetadataApiManager(IsolatedAsyncioTestCase):
    """Test the MetadataAPIManager class."""

    def setUp(self) -> None:
        """Set up test cases"""
        self.api = MetadataAPIManager(host="test_url.com", network="cosmos")
        self.mock_response_data = {
            "meta": {
                "@id": "http://fdri.ceh.ac.uk/id/network/cosmos.json",
                "publisher": "UK Centre for Ecology & Hydrology",
                "license": "http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
                "licenseName": "OGL 3",
                "comment": "",
                "version": "1.0.0",
            },
            "items": [
                {
                    "@id": "http://fdri.ceh.ac.uk/id/network/cosmos",
                    "contains": [{"@id": "http://fdri.ceh.ac.uk/id/site/cosmos-sheep", "label": ["Sheepdrove"]}],
                }
            ],
        }

    async def test_make_api_call_success(self) -> None:
        """Test successful API response."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_request = Request(method="get", url="test_url.com")
            mock_response = Response(200, json=self.mock_response_data, request=mock_request)

            mock_get.return_value = mock_response

            result = await self.api._make_api_call("test_url.com")

            self.assertEqual(result, self.mock_response_data)

    async def test_make_api_call_general_error(self) -> None:
        """Test handling of general errors."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_error = HTTPError("API Error")
            mock_get.side_effect = mock_error

            with self.assertRaises(HTTPError) as context:
                await self.api._make_api_call("test_url.com")

            self.assertEqual(str(context.exception), "API Error")

    async def test_make_api_call_404_error(self) -> None:
        """Test handling of 404 errors."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_error = HTTPStatusError("404 Error", request="test_request", response=404)
            mock_get.side_effect = mock_error

            with self.assertRaises(HTTPError) as context:
                await self.api._make_api_call("test_url.com")

            self.assertEqual(str(context.exception), "404 Error")

    async def test_make_api_call_timeout_error(self) -> None:
        """Test handling of timeout errors."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_error = TimeoutException("timed_out")
            mock_get.side_effect = mock_error

            with self.assertRaises(HTTPError) as context:
                await self.api._make_api_call("test_url.com")

            self.assertEqual(str(context.exception), "timed_out")

    async def test_make_api_call_invalid_json(self) -> None:
        """Test handling of invalid JSON response."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_request = Request(method="get", url="test_url.com")
            mock_response = Response(200, json=self.mock_response_data, request=mock_request)
            mock_response._content = b"invalid json"
            mock_get.return_value = mock_response

            with self.assertRaises(json.JSONDecodeError):
                await self.api._make_api_call("test_url.com")


@patch.object(MetadataAPIManager, "_make_api_call")
class TestPaginatedAPICall(IsolatedAsyncioTestCase):
    """NOTES - DELETE LATER

    - limit not in api response
    - limit in api response
        - num items < limit stated
        - num items > limit stated
        - num items == limit stated

    - Need a way to mock pagination calls
        - at least 2 loops, second returns items < limit
    - parameter for page size? <- makes for easier testing

    """

    def setUp(self) -> None:
        self.host_url = "test_url.com"
        self.api = MetadataAPIManager(host=self.host_url, network="cosmos")

    async def test_no_pagination_required_limit_field_not_present(self, mock_metadata_api: MagicMock) -> None:
        """Check the entire API response is returned if no pagination is required."""
        expected_response = {"meta": {}, "items": [{"key_1": "value_1"}]}
        mock_api_data = {self.host_url: expected_response}
        mock_metadata_api.side_effect = MockMetadataAPI(api_data=mock_api_data)

        result = await self.api._make_paginated_api_call(self.host_url)

        assert result == expected_response
        assert mock_metadata_api.call_count == 1

    async def test_no_pagination_required_num_items_below_limit(self, mock_metadata_api: MagicMock) -> None:
        """Check no extra pagination calls are made if fewer items than the page size limit are returned."""
        expected_response = {"meta": {"limit": 2}, "items": [{"key_1": "value_1"}]}
        mock_api_data = {self.host_url: expected_response}
        mock_metadata_api.side_effect = MockMetadataAPI(api_data=mock_api_data)

        result = await self.api._make_paginated_api_call(self.host_url)

        assert result == expected_response
        assert mock_metadata_api.call_count == 1

    async def test_pagination_required(self, mock_metadata_api: MagicMock) -> None:
        """Check the pagination logic is called when required."""
        expected_response = {
            "meta": {"limit": 2},
            "items": [{"key_1": "value_1"}, {"key_2": "value_2"}, {"key_3", "value_3"}],
        }
        mock_api_data = {self.host_url: expected_response}
        mock_metadata_api.side_effect = MockMetadataAPI(api_data=mock_api_data)

        result = await self.api._make_paginated_api_call(self.host_url, page_size=2)

        assert result == expected_response
        assert mock_metadata_api.call_count == 2
