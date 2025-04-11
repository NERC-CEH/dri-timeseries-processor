import unittest
import json
from metadata_manager.transformers import extract_cosmos_site_ids, extract_site_ids, extract_dataset_metadata
from unittest.mock import patch
from pathlib import Path


def load_json(fpath):
    with open(fpath) as file:
        data = json.load(file)
    return data

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
    """Test the extract_site_ids function"""

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

    @patch('metadata_manager.transformers.extract_cosmos_site_ids')
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


class TestExtractDatasetMetadata(unittest.TestCase):
    """Test the extract _dataset_metadata function."""

    def setUp(self):
        self.sample_dataset_response = (
            load_json(Path(Path(__file__).parents[0], "sample_test_data", "dataset_response.json"))
        )
    
    def test_extract_two_items(self):
        """Test two items are correctly extracted."""

        item_one =   {
            "output": {
                "resolution": "PT30M",
                "periodicity": "PT30M",
                "sourceBucket": "ukceh-fdri-staging-timeseries-qc",
                "sourceDataset": "PROCESSED_DATA_30MIN",
                "sourceColumnName": "TA",
                "sourceSite": "cosmos-alic1"
            },
            "ts_id": "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-ta_30min_processed",
            "ts_def": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_processed"
            }
        
        item_two =   {
            "output": {
                "resolution": "PT30M",
                "periodicity": "PT30M",
                "sourceBucket": "ukceh-fdri-staging-timeseries-qc",
                "sourceDataset": "PROCESSED_DATA_30MIN",
                "sourceColumnName": "TA",
                "sourceSite": "cosmos-bunny"
            },
            "ts_id": "http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-ta_30min_processed",
            "ts_def": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_processed"
        }

        expected = [item_one, item_two]

        result = extract_dataset_metadata(self.sample_dataset_response, "output")

        assert result == expected

