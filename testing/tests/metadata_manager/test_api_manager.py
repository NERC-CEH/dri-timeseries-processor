from unittest.mock import patch
from unittest.async_case import IsolatedAsyncioTestCase
import json
from httpx import HTTPError, HTTPStatusError, Response, Request, TimeoutException
from metadata_manager.api_manager import MetadataAPIManager


class TestMetadataApiManager(IsolatedAsyncioTestCase):
    """Test the MetadataAPIManager class."""
    def setUp(self):
        """Set up test cases"""
        self.api = MetadataAPIManager(host='test_url.com', network="cosmos")
        self.mock_response_data = {
            "meta":
                {
                    "@id":"http://fdri.ceh.ac.uk/id/network/cosmos.json",
                    "publisher":"UK Centre for Ecology & Hydrology",
                    "license":"http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
                    "licenseName":"OGL 3",
                    "comment":"",
                    "version":"1.0.0"},
            "items":
                [
                    {
                        "@id":"http://fdri.ceh.ac.uk/id/network/cosmos",
                        "contains":
                            [
                                {
                                    "@id":"http://fdri.ceh.ac.uk/id/site/cosmos-sheep",
                                    "label":["Sheepdrove"]
                                }
                            ]
                    }
                ]
            }

    async def test_make_api_call_success(self):
        """Test successful API response."""
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_request = Request(method='get', url='test_url.com')
            mock_response = Response(200, json=self.mock_response_data, request=mock_request)

            mock_get.return_value = mock_response

            result = await self.api._make_api_call('test_url.com')

            self.assertEqual(result, self.mock_response_data)

    async def test_make_api_call_general_error(self):
        """Test handling of general errors."""
        with patch('httpx.AsyncClient.get') as mock_get:
            
            mock_error = HTTPError("API Error")
            mock_get.side_effect = mock_error

            with self.assertRaises(HTTPError) as context:
                await self.api._make_api_call('test_url.com')
            
            self.assertEqual(str(context.exception), "API Error")

    async def test_make_api_call_404_error(self):
        """Test handling of 404 errors."""
        with patch('httpx.AsyncClient.get') as mock_get:
            
            mock_error = HTTPStatusError("404 Error", request='test_request', response=404)
            mock_get.side_effect = mock_error

            with self.assertRaises(HTTPError) as context:
                await self.api._make_api_call('test_url.com')
            
            self.assertEqual(str(context.exception), "404 Error")

    async def test_make_api_call_timeout_error(self):
        """Test handling of timeout errors."""
        with patch('httpx.AsyncClient.get') as mock_get:
            
            mock_error = TimeoutException("timed_out")
            mock_get.side_effect = mock_error

            with self.assertRaises(HTTPError) as context:
                await self.api._make_api_call('test_url.com')
            
            self.assertEqual(str(context.exception), "timed_out")

    async def test_make_api_call_invalid_json(self):
        """Test handling of invalid JSON response."""
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_request = Request(method='get', url='test_url.com')
            mock_response = Response(200, json=self.mock_response_data, request=mock_request)
            mock_response._content = b'invalid json'
            mock_get.return_value = mock_response
            
            with self.assertRaises(json.JSONDecodeError):
                await self.api._make_api_call('test_url.com')
