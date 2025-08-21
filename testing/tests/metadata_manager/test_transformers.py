import json
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from metadata_manager.models.schemas.datasets import TimeseriesDatasetResponse, TimeSeriesType
from metadata_manager.models.schemas.sites import SitesResponse
from metadata_manager.transformers import (
    extract_cosmos_site_ids,
    extract_site_ids,
    extract_timeseries_id_metadata,
    extract_timeseries_methodology_metadata,
)


def load_json(fpath: str) -> Dict[str, Any]:
    with open(fpath) as file:
        data = json.load(file)
    return data


class TestExtractCOSMOSSiteIds(unittest.TestCase):
    """Test the extract_cosmos_site_ids function."""

    def setUp(self) -> None:
        """Set up test cases"""

        self.sample_raw_data = {
            "items": [
                {
                    "@id": "http://fdri.ceh.ac.uk/id/network/cosmos",
                    "contains": [
                        {"@id": "http://fdri.ceh.ac.uk/id/site/cosmos-site123", "label": ["Cardington"]},
                        {"@id": "http://fdri.ceh.ac.uk/id/site/cosmos-site456", "label": ["Cwm Garw"]},
                    ],
                    "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/EnvironmentalMonitoringNetwork"}],
                    "label": ["COSMOS Network"],
                }
            ]
        }

    def test_extract_site_ids_cosmos_uri(self) -> None:
        """Test extracting site IDs from cosmos URI"""

        validated_data = SitesResponse.model_validate(self.sample_raw_data)
        result = extract_cosmos_site_ids(validated_data)
        self.assertEqual(result, ["SITE123", "SITE456"])

    def test_extract_site_ids_cosmos_uri_fail(self) -> None:
        """Test extracting site IDs from cosmos URI where one fails."""

        self.sample_raw_data["items"][0]["contains"][1]["@id"] = "http://fdri.ceh.ac.uk/id/site/fdri-site456"
        validated_data = SitesResponse.model_validate(self.sample_raw_data)
        result = extract_cosmos_site_ids(validated_data)
        self.assertEqual(result, ["SITE123"])


class TestExtractSiteIds(unittest.TestCase):
    """Test the extract_site_ids function"""

    def setUp(self) -> None:
        """Set up test cases"""

        self.sample_site1 = {
            "@id": "http://fdri.ceh.ac.uk/id/site/cosmos-site123",
            "label": ["Test Site1"],
            "comment": ["Test Comment1"],
        }

        self.sample_site2 = {
            "@id": "http://fdri.ceh.ac.uk/id/site/cosmos-site456",
            "label": ["Test Site2"],
            "comment": ["Test Comment2"],
        }

        self.sample_raw_data = {"items": [{"contains": [self.sample_site1, self.sample_site2]}]}

    @patch("metadata_manager.transformers.extract_cosmos_site_ids")
    def test_extract_site_ids_valid_network(self, mock_extract_cosmos_site_ids: MagicMock) -> None:
        """Test extracting site IDs from cosmos network"""
        mock_extract_cosmos_site_ids.return_value = ["SITE123", "SITE456"]
        result = extract_site_ids(self.sample_raw_data, "cosmos")
        self.assertEqual(result, ["SITE123", "SITE456"])

    def test_extract_site_ids_unsupported_network(self) -> None:
        """Test extracting site IDs from an unsupported network"""

        with self.assertRaises(ValueError) as context:
            extract_site_ids(self.sample_raw_data, "unsupported_network")
        self.assertEqual(str(context.exception), "Network unsupported_network not supported.")


class TestExtractTimeseriesIDMetadata(unittest.TestCase):
    """Test the extract_timeseries_id_metadata function."""

    def setUp(self) -> None:
        self.sample_dataset_response = load_json(
            Path(Path(__file__).parents[0], "sample_test_data", "dataset_response.json")
        )

    def test_extract_two_items(self) -> None:
        """Test two items are correctly extracted."""

        item_one = {
            "ts_def": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_processed",
            "resolution": "PT30M",
            "periodicity": "PT30M",
            "processing_level": "processed",
            "sourceBucket": "ukceh-fdri-staging-timeseries-processed",
            "sourceDataset": "PROCESSED_DATA_30MIN",
            "sourceColumnName": "TA",
            "sourceSite": "ALIC1",
            "load": False,
        }

        item_two = {
            "ts_def": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_processed",
            "resolution": "PT30M",
            "periodicity": "PT30M",
            "processing_level": "processed",
            "sourceBucket": "ukceh-fdri-staging-timeseries-processed",
            "sourceDataset": "PROCESSED_DATA_30MIN",
            "sourceColumnName": "TA",
            "sourceSite": "BUNNY",
            "load": False,
        }

        expected = {
            "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-ta_30min_processed": item_one,
            "http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-ta_30min_processed": item_two,
        }

        result = extract_timeseries_id_metadata(TimeseriesDatasetResponse.model_validate(self.sample_dataset_response))

        assert result == expected


class TestExtractTimeseriesMethodologyMetadata(unittest.TestCase):
    def test_extract_timeseries_methodology_metadata(self) -> None:
        input_data = TimeSeriesType(
            **{
                "@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/pe_30min_processed",
                "processingLevel": {"@id": "http://fdri.ceh.ac.uk/ref/common/processing-level/processed"},
                "measure": {
                    "@id": "http://fdri.ceh.ac.uk/ref/common/measure/pe-mm-total_prec-pt30m-pt30m",
                    "variable": {
                        "@id": "http://fdri.ceh.ac.uk/ref/common/cop/pe",
                        "prefLabel": ["Potential Evaporation"],
                    },
                    "hasUnit": {"@id": "http://fdri.ceh.ac.uk/ref/common/unit/mm", "prefLabel": ["mm"]},
                    "aggregation": {
                        "@id": "http://fdri.ceh.ac.uk/ref/common/aggregation/total_prec-pt30m-pt30m",
                        "valueStatistic": {"@id": "http://fdri.ceh.ac.uk/ref/common/statistic/total_prec"},
                        "periodicity": "PT30M",
                        "resolution": "PT30M",
                    },
                },
                "methodology": {
                    "@id": "http://fdri.ceh.ac.uk/id/plan/cosmos-pe_30min_processed-derivation",
                    "uses": [
                        {"@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/rn_30min_processed"},
                        {"@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ws_30min_processed"},
                        {"@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_processed"},
                        {"@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/rh_30min_processed"},
                        {"@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/pa_30min_processed"},
                        {"@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/g2_30min_processed"},
                        {"@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/g1_30min_processed"},
                    ],
                    "configuration": {
                        "@id": "http://fdri.ceh.ac.uk/id/data-processing-configuration/pe_30min_processed",
                        "type": {"@id": "http://fdri.ceh.ac.uk/ref/common/configuration-type/calculate"},
                        "hasCurrentConfiguration": [
                            {
                                "@id": "http://fdri.ceh.ac.uk/id/configuration-item/pe_30min_processed-current",
                                "method": {"@id": "http://fdri.ceh.ac.uk/ref/common/method/calculate-calculate_pe"},
                            }
                        ],
                    },
                },
            }
        )

        expected = {
            "method_type": "calculate",
            "method": "calculate-calculate_pe",
            "inputs": [
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/rn_30min_processed",
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ws_30min_processed",
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_processed",
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/rh_30min_processed",
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/pa_30min_processed",
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/g2_30min_processed",
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/g1_30min_processed",
            ],
        }

        actual = extract_timeseries_methodology_metadata(input_data)

        assert actual == expected

    def test_no_methodology(self) -> None:
        input_data = TimeSeriesType(
            **{
                "@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/pe_30min_processed",
                "processingLevel": {"@id": "http://fdri.ceh.ac.uk/ref/common/processing-level/processed"},
                "measure": {
                    "@id": "http://fdri.ceh.ac.uk/ref/common/measure/pe-mm-total_prec-pt30m-pt30m",
                    "variable": {
                        "@id": "http://fdri.ceh.ac.uk/ref/common/cop/pe",
                        "prefLabel": ["Potential Evaporation"],
                    },
                    "hasUnit": {"@id": "http://fdri.ceh.ac.uk/ref/common/unit/mm", "prefLabel": ["mm"]},
                    "aggregation": {
                        "@id": "http://fdri.ceh.ac.uk/ref/common/aggregation/total_prec-pt30m-pt30m",
                        "valueStatistic": {"@id": "http://fdri.ceh.ac.uk/ref/common/statistic/total_prec"},
                        "periodicity": "PT30M",
                        "resolution": "PT30M",
                    },
                },
            }
        )

        expected = {"inputs": []}

        actual = extract_timeseries_methodology_metadata(input_data)

        assert actual == expected

    def test_error_when_no_inputs_for_processed_data(self) -> None:
        input_data = TimeSeriesType(
            **{
                "@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/precip_30min_processed",
                "processingLevel": {"@id": "http://fdri.ceh.ac.uk/ref/common/processing-level/processed"},
                "measure": {
                    "@id": "http://fdri.ceh.ac.uk/ref/common/measure/precipitation-mm-total_prec-pt30m-pt30m",
                    "variable": {
                        "@id": "http://fdri.ceh.ac.uk/ref/common/cop/precipitation",
                        "prefLabel": ["Precipitation"],
                    },
                    "hasUnit": {"@id": "http://fdri.ceh.ac.uk/ref/common/unit/mm", "prefLabel": ["mm"]},
                    "aggregation": {
                        "@id": "http://fdri.ceh.ac.uk/ref/common/aggregation/total_prec-pt30m-pt30m",
                        "valueStatistic": {"@id": "http://fdri.ceh.ac.uk/ref/common/statistic/total_prec"},
                        "periodicity": "PT30M",
                        "resolution": "PT30M",
                    },
                },
                "methodology": {
                    "@id": "http://fdri.ceh.ac.uk/id/plan/cosmos-precip_30min_processed-derivation",
                    "uses": [],
                    "configuration": {
                        "@id": "http://fdri.ceh.ac.uk/id/data-processing-configuration/precip_30min_processed",
                        "type": {"@id": "http://fdri.ceh.ac.uk/ref/common/configuration-type/process"},
                        "hasCurrentConfiguration": [
                            {"@id": "http://fdri.ceh.ac.uk/id/configuration-item/precip_30min_processed-current"}
                        ],
                    },
                },
            }
        )

        expected_error = (
            "Processed timeseries definition http://fdri.ceh.ac.uk/ref/cosmos/time-series/precip_30min_processed "
            "should have exactly one input."
        )

        with pytest.raises(ValueError, match=expected_error):
            extract_timeseries_methodology_metadata(input_data)

    def test_error_when_no_method_type_for_aggregate_or_calculate(self) -> None:
        input_data = TimeSeriesType(
            **{
                "@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/rn_30min_processed",
                "processingLevel": {"@id": "http://fdri.ceh.ac.uk/ref/common/processing-level/processed"},
                "measure": {
                    "@id": "http://fdri.ceh.ac.uk/ref/common/measure/rn-wm-2-mean_prec-pt30m-pt30m",
                    "variable": {"@id": "http://fdri.ceh.ac.uk/ref/common/cop/rn", "prefLabel": ["Net radiation"]},
                    "hasUnit": {"@id": "http://fdri.ceh.ac.uk/ref/common/unit/wm-2", "prefLabel": ["Wm-2"]},
                    "aggregation": {
                        "@id": "http://fdri.ceh.ac.uk/ref/common/aggregation/mean_prec-pt30m-pt30m",
                        "valueStatistic": {"@id": "http://fdri.ceh.ac.uk/ref/common/statistic/mean_prec"},
                        "periodicity": "PT30M",
                        "resolution": "PT30M",
                    },
                },
                "methodology": {
                    "@id": "http://fdri.ceh.ac.uk/id/plan/cosmos-rn_30min_processed-derivation",
                    "uses": [
                        {"@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/swin_30min_processed"},
                        {"@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/lwin_30min_processed"},
                        {"@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/swout_30min_processed"},
                        {"@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/lwout_30min_processed"},
                    ],
                    "configuration": {
                        "@id": "http://fdri.ceh.ac.uk/id/data-processing-configuration/rn_30min_processed",
                        "type": {"@id": "http://fdri.ceh.ac.uk/ref/common/configuration-type/calculate"},
                    },
                },
            }
        )

        expected_error = "Method type 'calculate' requires a method to be specified."

        with pytest.raises(ValueError, match=expected_error):
            extract_timeseries_methodology_metadata(input_data)
