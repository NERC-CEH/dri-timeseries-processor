import unittest
import json
from metadata_manager.models.schemas.data_processing_configurations import DataProcessingConfigurations
from metadata_manager.models.schemas.datasets import TimeseriesDatasetResponse
from metadata_manager.transformers import (
    extract_cosmos_site_ids,
    extract_site_ids,
    extract_timeseries_id_metadata,
    extract_timeseries_definition_metadata,
    extract_dep_ts,
    extract_correction_dependencies,
    extract_qc_dependencies,
    extract_infill_dependencies,
)
from metadata_manager.models.schemas.derivations import TimeseriesDerivationResponse
from metadata_manager.models.schemas.sites import SitesResponse
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

        self.sample_raw_data = {
            "items":
                [
                    {
                    "@id": "http://fdri.ceh.ac.uk/id/network/cosmos",
                    "contains":
                    [
                        {
                            "@id": "http://fdri.ceh.ac.uk/id/site/cosmos-site123",
                            "label":
                            [
                                "Cardington"
                            ]
                        },
                        {
                            "@id": "http://fdri.ceh.ac.uk/id/site/cosmos-site456",
                            "label":
                            [
                                "Cwm Garw"
                            ]
                        }
                    ],
                    "@type":
                    [
                        {
                            "@id": "http://fdri.ceh.ac.uk/vocab/metadata/EnvironmentalMonitoringNetwork"
                        }
                    ],
                    "label":
                    [
                        "COSMOS Network"
                    ]
        }
        ]
        }

    def test_extract_site_ids_cosmos_uri(self):
        """Test extracting site IDs from cosmos URI"""

        validated_data = SitesResponse.model_validate(self.sample_raw_data)
        result = extract_cosmos_site_ids(validated_data)
        self.assertEqual(result, ['SITE123', 'SITE456'])

    def test_extract_site_ids_cosmos_uri_fail(self):
        """Test extracting site IDs from cosmos URI where one fails."""

        self.sample_raw_data['items'][0]['contains'][1]['@id'] = 'http://fdri.ceh.ac.uk/id/site/fdri-site456'
        validated_data = SitesResponse.model_validate(self.sample_raw_data)
        result = extract_cosmos_site_ids(validated_data)
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


class TestExtractTimeseriesIDMetadata(unittest.TestCase):
    """Test the extract_timeseries_id_metadata function."""

    def setUp(self):
        self.sample_dataset_response = (
            load_json(Path(Path(__file__).parents[0], "sample_test_data", "dataset_response.json"))
        )
    
    def test_extract_two_items(self):
        """Test two items are correctly extracted."""

        item_one = {
            "ts_def": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_processed",
            "resolution": "PT30M",
            "periodicity": "PT30M",
            "processing_level": "processed",
            "sourceBucket": "ukceh-fdri-staging-timeseries-processed",
            "sourceDataset": "PROCESSED_DATA_30MIN",
            "sourceColumnName": "TA",
            "sourceSite": "ALIC1"
        }
        
        item_two =   {
            "ts_def": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_processed",
            "resolution": "PT30M",
            "periodicity": "PT30M",
            "processing_level": "processed",
            "sourceBucket": "ukceh-fdri-staging-timeseries-processed",
            "sourceDataset": "PROCESSED_DATA_30MIN",
            "sourceColumnName": "TA",
            "sourceSite": "BUNNY"
        }

        expected = {"http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-ta_30min_processed": item_one,
                    "http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-ta_30min_processed": item_two}

        result = extract_timeseries_id_metadata(TimeseriesDatasetResponse.model_validate(self.sample_dataset_response))

        assert result == expected


class TestExtractTimeseriesDefinitionMetadata(unittest.TestCase):
    """Test the extract_timeseries_definition_metadata function."""

    def setUp(self):
        self.sample_dataset_response = (
            load_json(Path(Path(__file__).parents[0], "sample_test_data", "timeseries_definition_response.json"))
        )
    
    def test_extract_ts_def_metadata_with_methodology(self):
        """Test the extract_timeseries_definition_metadata function when the response
        contains a methodology section.
        """
        # Load the data into the pyantic model
        model_output = TimeseriesDerivationResponse.model_validate(self.sample_dataset_response)

        expected = {
            'method_type': 'calculate',
            'inputs': ['http://fdri.ceh.ac.uk/ref/cosmos/time-series/pe_30min_processed', 'http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_processed'],
            'method': 'calculate-calc_daily_pe'}
        
        result = extract_timeseries_definition_metadata(model_output)

        assert result == expected

    def test_extract_ts_def_metadata_with_no_methodology(self):
        """Test the extract_timeseries_definition_metadata function when the response
        doesnt contain a methodology section.
        """
        # Remove methodology section
        del self.sample_dataset_response['items'][0]['methodology']

        # Load the data into the pyantic model
        model_output = TimeseriesDerivationResponse.model_validate(self.sample_dataset_response)

        expected = {'inputs': []}
        
        result = extract_timeseries_definition_metadata(model_output)

        assert result == expected

    def test_process_meth_with_no_inputs(self):
        """Test the extract_timeseries_definition_metadata function raises an error when the
        response contains a methodology section with a process method type but no inputs.
        """
        # Set the methodology section to a process method type
        self.sample_dataset_response["items"][0]["methodology"]["configuration"]["type"]["@id"] = 'http://fdri.ceh.ac.uk/ref/common/configuration-type/process'
        # Remove inputs from the methodology section
        self.sample_dataset_response['items'][0]['methodology']['uses'] = []

        # Load the data into the pyantic model
        model_output = TimeseriesDerivationResponse.model_validate(self.sample_dataset_response)

        with self.assertRaises(ValueError) as context:
            extract_timeseries_definition_metadata(model_output)

    def test_process_meth_with_more_than_one_inputs(self):
        """Test the extract_timeseries_definition_metadata function raises an error when the
        response contains a methodology section with a process method type but no inputs.
        """
        # Set the methodology section to a process method type
        self.sample_dataset_response["items"][0]["methodology"]["configuration"]["type"]["@id"] = 'http://fdri.ceh.ac.uk/ref/common/configuration-type/process'
        # Remove inputs from the methodology section
        self.sample_dataset_response['items'][0]['methodology']['uses'] = [
            {'@id': 'http://fdri.ceh.ac.uk/ref/cosmos/time-series/pe_30min_processed'},
            {'@id': 'http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_processed'}
        ]

        # Load the data into the pyantic model
        model_output = TimeseriesDerivationResponse.model_validate(self.sample_dataset_response)

        with self.assertRaises(ValueError) as context:
            extract_timeseries_definition_metadata(model_output)

    def test_no_method_with_agg_method_type(self):
        """Test the extract_timeseries_definition_metadata function raises an error when the
        response contains method type 'aggregate' but no method.
        """
        # Set the methodology section to a aggregate method type
        self.sample_dataset_response["items"][0]["methodology"]["configuration"]["type"]["@id"] = 'http://fdri.ceh.ac.uk/ref/common/configuration-type/aggregate'
        # Remove the method
        del self.sample_dataset_response['items'][0]['methodology']['configuration']["hasCurrentConfiguration"][0]["method"]["@id"]

        # Load the data into the pyantic model
        model_output = TimeseriesDerivationResponse.model_validate(self.sample_dataset_response)

        with self.assertRaises(ValueError) as context:
            extract_timeseries_definition_metadata(model_output)

    def test_no_method_with_calc_method_type(self):
        """Test the extract_timeseries_definition_metadata function raises an error when the
        response contains method type 'calculate' but no method.
        """
        # Set the methodology section to a aggregate method type
        self.sample_dataset_response["items"][0]["methodology"]["configuration"]["type"]["@id"] = 'http://fdri.ceh.ac.uk/ref/common/configuration-type/calculate'
        # Remove the method
        del self.sample_dataset_response['items'][0]['methodology']['configuration']["hasCurrentConfiguration"][0]["method"]["@id"]

        # Load the data into the pyantic model
        model_output = TimeseriesDerivationResponse.model_validate(self.sample_dataset_response)

        with self.assertRaises(ValueError) as context:
            extract_timeseries_definition_metadata(model_output)


class TestExtractDepTs(unittest.TestCase):
    """Test the extract_dep_ts function."""

    def setUp(self):
        self.sample_dataset_response = (
            load_json(Path(Path(__file__).parents[0], "sample_test_data", "qc_configs.json"))
        )
    
    def test_extract_dep_ts(self):
        """Test the extract_dep_ts function extracts the correct dependent timeseries IDs."""
        # Load the data into the pyantic model
        model_output = DataProcessingConfigurations.model_validate(self.sample_dataset_response)
        ts_ids = extract_dep_ts(model_output, "dep_ts")

        expected_ts_ids = [
            'http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-tnr01c_30min_raw',
            'http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-scans_30min_raw',
            'http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-battv_30min_raw'
        ]

        self.assertEqual(ts_ids, expected_ts_ids)


class TestExtractCorrectionDependencies(unittest.TestCase):
    """Test the extract_correction_dependencies function."""

    def setUp(self):
        self.sample_dataset_response = (
            load_json(Path(Path(__file__).parents[0], "sample_test_data", "correction_configs.json"))
        )
    
    def test_extract_correction_dependencies(self):
        """Test the extract_correction_dependencies function extracts the correct dependencies."""
        # Load the data into the pyantic model
        model_output = DataProcessingConfigurations.model_validate(self.sample_dataset_response)
        dependencies = extract_correction_dependencies(model_output)

        expected_dependencies = [
            'http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-lwout_unc_30min_raw',
            'http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-ta_30min_raw'
        ]

        self.assertEqual(dependencies, expected_dependencies)


class TestExtractQcDependencies(unittest.TestCase):
    """Test the extract_qc_dependencies function."""

    def setUp(self):
        self.sample_dataset_response = (
            load_json(Path(Path(__file__).parents[0], "sample_test_data", "qc_configs.json"))
        )
    
    def test_extract_qc_dependencies(self):
        """Test the extract_qc_dependencies function extracts the correct dependencies."""
        # Load the data into the pyantic model
        model_output = DataProcessingConfigurations.model_validate(self.sample_dataset_response)
        dependencies = extract_qc_dependencies(model_output)

        expected_dependencies = [
            'http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-tnr01c_30min_raw',
            'http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-scans_30min_raw',
            'http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-battv_30min_raw'
        ]

        self.assertEqual(dependencies, expected_dependencies)


class TestExtractInfillDependencies(unittest.TestCase):
    """Test the extract_infill_dependencies function."""

    def setUp(self):
        self.sample_dataset_response = (
            load_json(Path(Path(__file__).parents[0], "sample_test_data", "infill_configs.json"))
        )
    
    def test_extract_infill_dependencies(self):
        """Test the extract_infill_dependencies function extracts the correct dependencies."""
        # Load the data into the pyantic model
        model_output = DataProcessingConfigurations.model_validate(self.sample_dataset_response)
        dependencies = extract_infill_dependencies(model_output)

        expected_dependencies = [
            "http://fdri.ceh.ac.uk/id/time-series/cosmos-holln-cts_mod2_30min_raw"
        ]

        self.assertEqual(dependencies, expected_dependencies)

