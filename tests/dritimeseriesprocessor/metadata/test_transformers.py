import unittest
from dritimeseriesprocessor.metadata.transformers import extract_cosmos_site_ids, extract_site_ids
from unittest.mock import patch


class TestExtractCOSMOSSiteIds(unittest.TestCase):
    """Test the extract_cosmos_site_ids function."""

    def setUp(self):
        """Set up test cases"""

        self.sample_site1 = {
            '@id': 'http://fdri.ceh.ac.uk/id/site/cosmos-site123',
            'label': ['Test Site1'],
            'comment': ['Test Comment1']
        }
        
        self.sample_site2 = {
            '@id': 'http://fdri.ceh.ac.uk/id/site/cosmos-site456',
            'label': ['Test Site2'],
            'comment': ['Test Comment2']
        }

        self.sample_raw_data = {
            'items': [{
                'contains': [self.sample_site1, self.sample_site2]
            }]
        }

    def test_extract_site_ids_cosmos_uri(self):
        """Test extracting site IDs from cosmos URI"""

        result = extract_cosmos_site_ids(self.sample_raw_data)
        self.assertEqual(result, ['SITE123', 'SITE456'])

    def test_extract_site_ids_cosmos_uri_fail(self):
        """Test extracting site IDs from cosmos URI where one fails."""

        self.sample_raw_data['items'][0]['contains'][1]['@id'] = 'http://fdri.ceh.ac.uk/id/site/fdri-site456'
        result = extract_cosmos_site_ids(self.sample_raw_data)
        self.assertEqual(result, ['SITE123'])


class TestExtractSiteIds(unittest.TestCase):
    """Test the extract_site_ids function."""

    def setUp(self):
        """Set up test cases"""

        self.sample_site1 = {
            '@id': 'http://fdri.ceh.ac.uk/id/site/cosmos-site123',
            'label': ['Test Site1'],
            'comment': ['Test Comment1']
        }
        
        self.sample_site2 = {
            '@id': 'http://fdri.ceh.ac.uk/id/site/cosmos-site456',
            'label': ['Test Site2'],
            'comment': ['Test Comment2']
        }

        self.sample_raw_data = {
            'items': [{
                'contains': [self.sample_site1, self.sample_site2]
            }]
        }

    @patch('dritimeseriesprocessor.metadata.transformers.extract_cosmos_site_ids')
    def test_extract_site_ids_valid_network(self, mock_extract_cosmos_site_ids):
        """Test extracting site IDs from cosmos network"""
        mock_extract_cosmos_site_ids.return_value = ['SITE123', 'SITE456']
        result = extract_site_ids(self.sample_raw_data, 'cosmos')
        self.assertEqual(result, ['SITE123', 'SITE456'])

    def test_extract_site_ids_unsupported_network(self):
        """Test extracting site IDs from an unsupported network"""

        with self.assertRaises(ValueError) as context:
            extract_site_ids(self.sample_raw_data, 'unsupported_network')
        self.assertEqual(str(context.exception), 'Network unsupported_network not supported.')
