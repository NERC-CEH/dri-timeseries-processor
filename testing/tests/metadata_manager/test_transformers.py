import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from metadata_manager.models.schemas.data_processing_configurations import DataProcessingConfigurations
from metadata_manager.models.schemas.datasets import TimeseriesDatasetResponse, TimeSeriesType
from metadata_manager.models.schemas.sites import SitesResponse
from metadata_manager.transformers import (
    extract_correction_dependencies,
    extract_cosmos_site_ids,
    extract_dep_ts,
    extract_infill_dependencies,
    extract_qc_dependencies,
    extract_site_ids,
    extract_timeseries_id_metadata,
    extract_timeseries_methodology_metadata,
)


def load_json(fpath: str) -> Dict[str, Any]:
    with open(fpath) as file:
        data = json.load(file)
    return data


class TestExtractCOSMOSSiteIds:
    """Test the extract_cosmos_site_ids function."""

    @property
    def sample_raw_data(self) -> Dict[str, Any]:
        """Set up test cases"""
        sample_raw_data = {
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
        return sample_raw_data

    def test_extract_site_ids_cosmos_uri(self) -> None:
        """Test extracting site IDs from cosmos URI"""

        validated_data = SitesResponse.model_validate(self.sample_raw_data)
        result = extract_cosmos_site_ids(validated_data)
        assert result == ["SITE123", "SITE456"]

    def test_extract_site_ids_cosmos_uri_fail(self) -> None:
        """Test extracting site IDs from cosmos URI where one fails."""
        sample_raw_data = self.sample_raw_data.copy()
        sample_raw_data["items"][0]["contains"][1]["@id"] = "http://fdri.ceh.ac.uk/id/site/fdri-site456"
        validated_data = SitesResponse.model_validate(sample_raw_data)

        result = extract_cosmos_site_ids(validated_data)
        assert result == ["SITE123"]


class TestExtractSiteIds:
    """Test the extract_site_ids function"""

    @property
    def sample_raw_data(self) -> None:
        """Set up test cases"""

        sample_site1 = {
            "@id": "http://fdri.ceh.ac.uk/id/site/cosmos-site123",
            "label": ["Test Site1"],
            "comment": ["Test Comment1"],
        }

        sample_site2 = {
            "@id": "http://fdri.ceh.ac.uk/id/site/cosmos-site456",
            "label": ["Test Site2"],
            "comment": ["Test Comment2"],
        }

        sample_raw_data = {"items": [{"contains": [sample_site1, sample_site2]}]}
        return sample_raw_data

    @patch("metadata_manager.transformers.extract_cosmos_site_ids")
    def test_extract_site_ids_valid_network(self, mock_extract_cosmos_site_ids: MagicMock) -> None:
        """Test extracting site IDs from cosmos network"""
        mock_extract_cosmos_site_ids.return_value = ["SITE123", "SITE456"]
        result = extract_site_ids(self.sample_raw_data, "cosmos")
        assert result == ["SITE123", "SITE456"]

    def test_extract_site_ids_unsupported_network(self) -> None:
        """Test extracting site IDs from an unsupported network"""

        with pytest.raises(ValueError, match="Network unsupported_network not supported."):
            extract_site_ids(self.sample_raw_data, "unsupported_network")


class TestExtractTimeseriesIDMetadata:
    """Test the extract_timeseries_id_metadata function."""

    @property
    def sample_dataset_response(self) -> None:
        sample_dataset_response = load_json(
            Path(Path(__file__).parents[0], "sample_test_data", "dataset_response.json")
        )
        return sample_dataset_response

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
            "inputs": [],
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
            "inputs": [],
        }

        expected = {
            "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-ta_30min_processed": item_one,
            "http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-ta_30min_processed": item_two,
        }

        result = extract_timeseries_id_metadata(TimeseriesDatasetResponse.model_validate(self.sample_dataset_response))

        assert result == expected


class TestExtractTimeseriesMethodologyMetadata:
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


class TestExtractDepTs:
    """Test the extract_dep_ts function."""

    @property
    def sample_dataset_response(self) -> Dict[str, Any]:
        sample_dataset_response = load_json(Path(Path(__file__).parents[0], "sample_test_data", "qc_configs.json"))
        return sample_dataset_response

    def test_extract_dep_ts(self) -> None:
        """Test the extract_dep_ts function extracts the correct dependent timeseries IDs."""
        # Load the data into the pyantic model
        model_output = DataProcessingConfigurations.model_validate(self.sample_dataset_response)
        ts_ids = extract_dep_ts(model_output, "dep_ts")

        expected_ts_ids = [
            "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-tnr01c_30min_raw",
            "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-battv_30min_raw",
            "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-scans_30min_raw",
        ]

        assert sorted(ts_ids) == sorted(expected_ts_ids)


class TestExtractCorrectionDependencies:
    """Test the extract_correction_dependencies function."""

    @property
    def sample_dataset_response(self) -> Dict[str, Any]:
        sample_dataset_response = load_json(
            Path(Path(__file__).parents[0], "sample_test_data", "correction_configs.json")
        )
        return sample_dataset_response

    def test_extract_correction_dependencies(self) -> None:
        """Test the extract_correction_dependencies function extracts the correct dependencies."""
        # Load the data into the pyantic model
        model_output = DataProcessingConfigurations.model_validate(self.sample_dataset_response)
        expected_dependencies = [
            "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-lwout_unc_30min_raw",
            "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-ta_30min_raw",
        ]

        dependencies = extract_correction_dependencies(model_output)

        assert sorted(expected_dependencies) == sorted(dependencies)


class TestExtractQcDependencies:
    """Test the extract_qc_dependencies function."""

    @property
    def sample_dataset_response(self) -> Dict[str, Any]:
        sample_dataset_response = load_json(Path(Path(__file__).parents[0], "sample_test_data", "qc_configs.json"))
        return sample_dataset_response

    def test_extract_qc_dependencies(self) -> None:
        """Test the extract_qc_dependencies function extracts the correct dependencies."""
        # Load the data into the pyantic model
        model_output = DataProcessingConfigurations.model_validate(self.sample_dataset_response)
        dependencies = extract_qc_dependencies(model_output)

        expected_dependencies = [
            "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-tnr01c_30min_raw",
            "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-scans_30min_raw",
            "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-battv_30min_raw",
        ]

        assert sorted(expected_dependencies) == sorted(dependencies)


class TestExtractInfillDependencies:
    """Test the extract_infill_dependencies function."""

    @property
    def sample_dataset_response(self) -> Dict[str, Any]:
        sample_dataset_response = load_json(Path(Path(__file__).parents[0], "sample_test_data", "infill_configs.json"))
        return sample_dataset_response

    def test_extract_infill_dependencies(self) -> None:
        """Test the extract_infill_dependencies function extracts the correct dependencies."""
        # Load the data into the pyantic model
        model_output = DataProcessingConfigurations.model_validate(self.sample_dataset_response)
        dependencies = extract_infill_dependencies(model_output)

        expected_dependencies = ["http://fdri.ceh.ac.uk/id/time-series/cosmos-holln-cts_mod2_30min_raw"]

        assert dependencies == expected_dependencies
