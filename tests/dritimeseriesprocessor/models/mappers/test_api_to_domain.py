from datetime import datetime
from unittest.mock import MagicMock

from tests.utils.fixture_helpers import TEST_DATA_API_VALID, load_json_file
from tests.utils.validation_helpers import valid_parses

from dritimeseriesprocessor.models.api_models.annotation import HasAnnotationItem
from dritimeseriesprocessor.models.api_models.data_processing_configuration import DataProcessingConfiguration
from dritimeseriesprocessor.models.api_models.dataset_observation import ObservationDatasetItem
from dritimeseriesprocessor.models.api_models.dataset_timeseries import TimeSeriesDatasetItem, TimeSeriesDatasetResponse
from dritimeseriesprocessor.models.api_models.shared import ArgumentItem, HasCurrentValue
from dritimeseriesprocessor.models.api_models.site import SiteItem
from dritimeseriesprocessor.models.domain_models.processing_config import (
    DataProcessingConfig,
    DataProcessingMethodConfig,
)
from dritimeseriesprocessor.models.domain_models.site_metadata import SiteMetadata
from dritimeseriesprocessor.models.domain_models.time_series_container import TimeSeriesContainer
from dritimeseriesprocessor.models.mappers.api_to_domain import (
    extract_annotations,
    extract_arguments,
    map_dataset_item,
    map_processing_config_item,
    map_processing_method_config,
    map_site_metadata,
)
from dritimeseriesprocessor.utils.enums import ConfigurationType, DatasetType, ProcessingLevel


class TestMapDatasetItem:
    def test_dataset_with_method(self) -> None:
        filename = TEST_DATA_API_VALID / "dataset_timeseries" / "cosmos_bunny_rn_1day_processed.json"
        api_model = valid_parses(load_json_file, filename, TimeSeriesDatasetResponse)

        site_metadata = MagicMock()
        site_metadata.alt_id = "BUNNY"
        site_metadata = {"http://fdri.ceh.ac.uk/id/site/cosmos-bunny": site_metadata}

        result = map_dataset_item(api_model.items[0], site_metadata)

        expected = TimeSeriesContainer(
            ts_id="http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-rn_1day_processed",
            network="cosmos",
            source_bucket="ukceh-dri-staging-processed",
            source_dataset="PROCESSED_DATA_1DAY",
            source_column="RN",
            source_site="cosmos-bunny",
            source_site_identifier="BUNNY",
            time_column_name="time",
            resolution="P1D",
            periodicity="P1D",
            processing_level=ProcessingLevel.PROCESSED,
            dataset_type=DatasetType.TIMESERIES_DATASET,
            correction_configs=set(),
            qc_configs=set(),
            infill_configs=set(),
            method_config=None,
            data=None,
        )

        assert result == expected

    def test_dataset_no_method(self) -> None:
        filename = TEST_DATA_API_VALID / "dataset_timeseries" / "cosmos_bunny_ta_30min_raw.json"
        api_model = valid_parses(load_json_file, filename, TimeSeriesDatasetResponse)

        site_metadata = MagicMock()
        site_metadata.alt_id = "BUNNY"
        site_metadata = {"http://fdri.ceh.ac.uk/id/site/cosmos-bunny": site_metadata}

        result = map_dataset_item(api_model.items[0], site_metadata)

        expected = TimeSeriesContainer(
            ts_id="http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-ta_30min_raw",
            network="cosmos",
            source_bucket="ukceh-dri-staging-ingested",
            source_dataset="LIVE_SOILMET_30MIN",
            source_column="TA",
            source_site="cosmos-bunny",
            source_site_identifier="BUNNY",
            time_column_name="time",
            resolution="PT30M",
            periodicity="PT30M",
            processing_level=ProcessingLevel.RAW,
            dataset_type=DatasetType.TIMESERIES_DATASET,
            correction_configs=set(),
            qc_configs=set(),
            infill_configs=set(),
            method_config=None,
            data=None,
        )

        assert result == expected

    def test_observation_dataset_item_source_fields_are_none(self) -> None:
        item = ObservationDatasetItem.model_validate(
            {
                "@id": "http://fdri.ceh.ac.uk/id/dataset/flux-plynl-raw",
                "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/ObservationDataset"}],
                "processingLevel": {"@id": "http://fdri.ceh.ac.uk/ref/common/processing-level/raw"},
                "measure": [
                    {
                        "@id": "http://fdri.ceh.ac.uk/id/measure/flux-plynl-raw",
                        "variable": {"@id": "http://fdri.ceh.ac.uk/ref/common/variable/flux-plynl-raw"},
                        "hasUnit": {"@id": "http://fdri.ceh.ac.uk/ref/common/unit/not-applicable"},
                        "aggregation": {
                            "@id": "http://fdri.ceh.ac.uk/ref/common/aggregation/flux-plynl-raw",
                            "periodicity": "PT30M",
                            "resolution": "PT30M",
                        },
                    }
                ],
                "originatingSite": [{"@id": "http://fdri.ceh.ac.uk/id/site/flux-plynl"}],
                "originatingProgramme": [{"@id": "http://fdri.ceh.ac.uk/id/programme/fdri"}],
            }
        )
        site_metadata = MagicMock()
        site_metadata.alt_id = "flux-plynl"
        all_site_metadata = {"http://fdri.ceh.ac.uk/id/site/flux-plynl": site_metadata}

        result = map_dataset_item(item, all_site_metadata)

        assert result.source_bucket is None
        assert result.source_dataset is None
        assert result.source_column is None
        assert result.time_column_name is None

    def test_observation_dataset_populates_dataset_type_and_distribution_url(self) -> None:
        item = TimeSeriesDatasetItem.model_validate(
            {
                "@id": "http://fdri.ceh.ac.uk/id/dataset/flux-plynl-raw",
                "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/ObservationDataset"}],
                "processingLevel": {"@id": "http://fdri.ceh.ac.uk/ref/common/processing-level/raw"},
                "measure": [
                    {
                        "@id": "http://fdri.ceh.ac.uk/id/measure/flux-plynl-raw",
                        "variable": {"@id": "http://fdri.ceh.ac.uk/ref/common/variable/flux-plynl-raw"},
                        "hasUnit": {"@id": "http://fdri.ceh.ac.uk/ref/common/unit/not-applicable"},
                        "aggregation": {
                            "@id": "http://fdri.ceh.ac.uk/ref/common/aggregation/flux-plynl-raw",
                            "periodicity": "PT30M",
                            "resolution": "PT30M",
                        },
                    }
                ],
                "distribution": [
                    {
                        "@id": "http://fdri.ceh.ac.uk/id/distribution/flux-plynl-raw",
                        "accessUrl": ["s3://ukceh-dri-staging-ingested/Flux/"],
                    }
                ],
                "originatingSite": [{"@id": "http://fdri.ceh.ac.uk/id/site/flux-plynl"}],
                "originatingProgramme": [{"@id": "http://fdri.ceh.ac.uk/id/programme/fdri"}],
            }
        )
        site_metadata = MagicMock()
        site_metadata.alt_id = "flux-plynl"
        all_site_metadata = {"http://fdri.ceh.ac.uk/id/site/flux-plynl": site_metadata}

        result = map_dataset_item(item, all_site_metadata)

        assert result.dataset_type == DatasetType.OBSERVATION_DATASET
        assert result.distribution_url == "s3://ukceh-dri-staging-ingested/Flux/"
        assert result.s3_bucket == "ukceh-dri-staging-ingested"
        assert result.s3_dataset_path == "Flux"

    def test_all_dependencies(self) -> None:
        """Test that the all_dependencies method returns valid list, when there are no qc/correction/infill configs"""

        method_config = DataProcessingConfig(
            ts_id="test_id",
            config_id="cfg",
            config_type=ConfigurationType.PROCESS,
            method_configs=[DataProcessingMethodConfig(method="m", params={"dep_ts": ["dep1", "dep2", "dep3"]})],
            annotations={},
        )

        item = TimeSeriesContainer(
            ts_id="test_id",
            network="network",
            source_bucket="bucket",
            source_dataset="dataset",
            source_column="col",
            source_site="a-site",
            source_site_identifier="BUNNY",
            time_column_name="time",
            resolution="PT30M",
            periodicity="PT30M",
            processing_level=ProcessingLevel.RAW,
            method_config=method_config,
        )
        assert item.all_dependencies() == ["dep1", "dep2", "dep3"]

    def test_all_dependencies_with_configs(self) -> None:
        """Test that the all_dependencies method returns valid list, when there are a qc/correction/infill configs"""

        method_config = DataProcessingConfig(
            ts_id="test_id",
            config_id="method_cfg",
            config_type=ConfigurationType.PROCESS,
            method_configs=[DataProcessingMethodConfig(method="m", params={"dep_ts": ["dep1", "dep2", "dep3"]})],
            annotations={},
        )
        qc_config = DataProcessingConfig(
            ts_id="test_id",
            config_id="qc_cfg",
            config_type=ConfigurationType.QUALITY_CONTROL,
            method_configs=[DataProcessingMethodConfig(method="m", params={"dep_ts": ["dep1", "dep4"]})],
            annotations={},
        )
        correction_config = DataProcessingConfig(
            ts_id="test_id",
            config_id="correction_cfg",
            config_type=ConfigurationType.CORRECTION,
            method_configs=[DataProcessingMethodConfig(method="m", params={"dep_ts": ["dep4", "dep5"]})],
            annotations={},
        )
        infill_config = DataProcessingConfig(
            ts_id="test_id",
            config_id="infill_cfg",
            config_type=ConfigurationType.INFILLING,
            method_configs=[DataProcessingMethodConfig(method="m", params={})],
            annotations={},
        )

        item = TimeSeriesContainer(
            ts_id="test_id",
            network="network",
            source_bucket="bucket",
            source_dataset="dataset",
            source_column="col",
            source_site="a-site",
            source_site_identifier="BUNNY",
            time_column_name="time",
            resolution="PT30M",
            periodicity="PT30M",
            processing_level=ProcessingLevel.RAW,
            correction_configs={correction_config},
            qc_configs={qc_config},
            infill_configs={infill_config},
            method_config=method_config,
        )
        assert item.all_dependencies() == ["dep1", "dep2", "dep3", "dep4", "dep5"]


class TestExtractArguments:
    def test_extract_arguments(self) -> None:
        """Test that arguments are extracted correctly from the configuration item api model."""
        data = [
            {
                "@id": "arg1_id",
                "hasValue": {
                    "@id": "value1_id",
                    "valueReference": [{"@id": "http://fdri.ceh.ac.uk/id/dataset/dependent-dataset_id"}],
                    "@type": [{"@id": "http://schema.org/PropertyValue"}],
                },
                "parameter": {"@id": "http://fdri.ceh.ac.uk/ref/common/parameter/dep_ts"},
                "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/ConfigurationArgument"}],
            },
            {
                "@id": "arg2_id",
                "hasValue": {
                    "@id": "value2_id",
                    "value": [10.5],
                    "@type": [{"@id": "http://schema.org/PropertyValue"}],
                },
                "parameter": {"@id": "http://fdri.ceh.ac.uk/ref/common/parameter/lt"},
                "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/ConfigurationArgument"}],
            },
            {
                "@id": "arg2_id",
                "hasStructuredValue": {
                    "@id": "arg2_id_structured_value",
                    "argument": [
                        {
                            "@id": "nested_arg1_id",
                            "hasValue": {
                                "@id": "nested_value1_id",
                                "valueReference": [{"@id": "http://fdri.ceh.ac.uk/id/dataset/dependent-dataset_id2"}],
                                "@type": [{"@id": "http://schema.org/PropertyValue"}],
                            },
                            "parameter": {"@id": "http://fdri.ceh.ac.uk/ref/common/parameter/dep_ts"},
                            "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/ConfigurationArgument"}],
                        },
                        {
                            "@id": "nested_arg2_id",
                            "hasValue": {
                                "@id": "nested_value2_id",
                                "value": [-999],
                                "@type": [{"@id": "http://schema.org/PropertyValue"}],
                            },
                            "parameter": {"@id": "http://fdri.ceh.ac.uk/ref/common/parameter/some_value.number"},
                            "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/ConfigurationArgument"}],
                        },
                    ],
                },
                "parameter": {"@id": "http://fdri.ceh.ac.uk/ref/common/parameter/some_value"},
                "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/ConfigurationArgument"}],
            },
        ]

        api_model = [ArgumentItem.model_validate(arg) for arg in data]
        result = extract_arguments(api_model, MagicMock())
        expected = {
            "dep_ts": "http://fdri.ceh.ac.uk/id/dataset/dependent-dataset_id",
            "lt": 10.5,
            "some_value": {
                "dep_ts": "http://fdri.ceh.ac.uk/id/dataset/dependent-dataset_id2",
                "some_value.number": -999,
            },
        }
        assert result == expected

    def test_extract_argument_hyphen_replace(self) -> None:
        """Test that arguments that have hyphens in the parameter name are replaced with an underscore."""
        data = [
            {
                "@id": "arg1_id",
                "hasValue": {
                    "@id": "value1_id",
                    "value": ["string value"],
                    "@type": [{"@id": "http://schema.org/PropertyValue"}],
                },
                "parameter": {"@id": "http://fdri.ceh.ac.uk/ref/common/parameter/a-string-value"},
                "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/ConfigurationArgument"}],
            },
        ]

        api_model = [ArgumentItem.model_validate(arg) for arg in data]
        result = extract_arguments(api_model, MagicMock())
        expected = {
            "a_string_value": "string value",
        }
        assert result == expected

    def test_extract_argument_multiple_values(self) -> None:
        """Test that arguments with the same parameter name extract into a list."""
        data = [
            {
                "@id": "arg1_id",
                "hasValue": {
                    "@id": "value1_id",
                    "value": [1],
                    "@type": [{"@id": "http://schema.org/PropertyValue"}],
                },
                "parameter": {"@id": "http://fdri.ceh.ac.uk/ref/common/parameter/same_name_value"},
                "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/ConfigurationArgument"}],
            },
            {
                "@id": "arg2_id",
                "hasValue": {
                    "@id": "value2_id",
                    "value": [2],
                    "@type": [{"@id": "http://schema.org/PropertyValue"}],
                },
                "parameter": {"@id": "http://fdri.ceh.ac.uk/ref/common/parameter/same_name_value"},
                "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/ConfigurationArgument"}],
            },
            {
                "@id": "arg3_id",
                "hasValue": {
                    "@id": "value3_id",
                    "value": [3],
                    "@type": [{"@id": "http://schema.org/PropertyValue"}],
                },
                "parameter": {"@id": "http://fdri.ceh.ac.uk/ref/common/parameter/same_name_value"},
                "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/ConfigurationArgument"}],
            },
        ]

        api_model = [ArgumentItem.model_validate(arg) for arg in data]
        result = extract_arguments(api_model, MagicMock())
        expected = {
            "same_name_value": [1, 2, 3],
        }
        assert result == expected


class TestMapProcessingMethodConfig:
    def test_simple_method_config(self) -> None:
        data = {
            "@id": "top_level_id",
            "argument": [
                {
                    "@id": "arg1_id",
                    "hasValue": {
                        "@id": "value1_id",
                        "value": [0.98787],
                    },
                    "parameter": {"@id": "http://fdri.ceh.ac.uk/ref/common/parameter/correction_factor"},
                    "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/ConfigurationArgument"}],
                }
            ],
            "method": {"@id": "http://fdri.ceh.ac.uk/ref/common/method/method_function_name"},
            "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/ConfigurationItem"}],
        }

        api_model = HasCurrentValue.model_validate(data)
        result = map_processing_method_config(api_model, MagicMock())

        expected = DataProcessingMethodConfig(
            method="method_function_name",
            params={
                "correction_factor": 0.98787,
            },
        )
        assert result == expected

    def test_method_config_with_obs_interval(self) -> None:
        data = {
            "@id": "top_level_id",
            "argument": [
                {
                    "@id": "arg1_id",
                    "hasValue": {
                        "@id": "value1_id",
                        "value": [0.98787],
                    },
                    "parameter": {"@id": "http://fdri.ceh.ac.uk/ref/common/parameter/correction_factor"},
                    "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/ConfigurationArgument"}],
                }
            ],
            "method": {"@id": "http://fdri.ceh.ac.uk/ref/common/method/method_function_name"},
            "observationInterval": {
                "@id": "http://fdri.ceh.ac.uk/id/observation-interval/id",
                "@type": [{"@id": "http://purl.org/dc/terms/PeriodOfTime"}],
                "endDate": "2020-08-17T15:00:00",
                "startDate": "2020-08-10T09:30:00",
            },
            "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/ConfigurationItem"}],
        }

        api_model = HasCurrentValue.model_validate(data)
        result = map_processing_method_config(api_model, MagicMock())

        expected = DataProcessingMethodConfig(
            method="method_function_name",
            params={
                "correction_factor": 0.98787,
            },
            start_date=datetime(2020, 8, 10, 9, 30, 0),
            end_date=datetime(2020, 8, 17, 15, 0, 0),
        )
        assert result == expected

    def test_infill_method_config(self) -> None:
        data = {
            "@id": "infill_id",
            "argument": [
                {
                    "@id": "arg1_id",
                    "hasValue": {
                        "@id": "value1_id",
                        "value": [1],
                        "@type": [{"@id": "http://schema.org/PropertyValue"}],
                    },
                    "parameter": {"@id": "http://fdri.ceh.ac.uk/ref/common/parameter/window"},
                    "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/Argument"}],
                },
                {
                    "@id": "arg2_id",
                    "hasValue": {
                        "@id": "value2_id",
                        "value": [6],
                        "@type": [{"@id": "http://schema.org/PropertyValue"}],
                    },
                    "parameter": {"@id": "http://fdri.ceh.ac.uk/ref/common/parameter/max-gap-size"},
                    "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/Argument"}],
                },
            ],
            "method": {"@id": "http://fdri.ceh.ac.uk/ref/common/method/linear_linear"},
            "observationInterval": {
                "@id": "obs_interval_id",
                "@type": [{"@id": "http://purl.org/dc/terms/PeriodOfTime"}],
                "startDate": "2013-01-01T00:30:00",
            },
            "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/ConfigurationItem"}],
        }

        api_model = HasCurrentValue.model_validate(data)
        result = map_processing_method_config(api_model, MagicMock())

        expected = DataProcessingMethodConfig(
            method="linear_linear",
            params={"window": 1, "max_gap_size": 6},
            start_date=datetime(2013, 1, 1, 0, 30, 0),
            end_date=None,
        )
        assert result == expected


class TestExtractAnnotations:
    def test_single_annotation(self) -> None:
        data = [
            {
                "@id": "top_level_id",
                "hasValue": {"@id": "value1_id", "value": [1], "@type": [{"@id": "http://schema.org/PropertyValue"}]},
                "property": {"@id": "http://fdri.ceh.ac.uk/ref/common/cop/data-processing-configuration-priority"},
                "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/Annotation"}],
            }
        ]

        api_model = [HasAnnotationItem.model_validate(ann) for ann in data]
        result = extract_annotations(api_model)
        expected = {"data_processing_configuration_priority": 1}
        assert result == expected

    def test_multiple_annotations(self) -> None:
        data = [
            {
                "@id": "top_level_id1",
                "hasValue": {"@id": "value1_id", "value": [1], "@type": [{"@id": "http://schema.org/PropertyValue"}]},
                "property": {"@id": "http://fdri.ceh.ac.uk/ref/common/cop/data-processing-configuration-priority"},
                "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/Annotation"}],
            },
            {
                "@id": "top_level_id2",
                "hasValue": {
                    "@id": "value2_id",
                    "value": ["abc"],
                    "@type": [{"@id": "http://schema.org/PropertyValue"}],
                },
                "property": {"@id": "http://fdri.ceh.ac.uk/ref/common/cop/another-annotation"},
                "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/Annotation"}],
            },
        ]

        api_model = [HasAnnotationItem.model_validate(ann) for ann in data]
        result = extract_annotations(api_model)
        expected = {"data_processing_configuration_priority": 1, "another_annotation": "abc"}
        assert result == expected


class TestMapProcessingConfigItem:
    def test_qc_processing_config(self) -> None:
        filename = TEST_DATA_API_VALID / "data_processing_configuration" / "cosmos_bunny_swin_30min_raw_qc.json"
        api_model = valid_parses(load_json_file, filename, DataProcessingConfiguration)

        result = map_processing_config_item(api_model.items[0], MagicMock())

        expected = DataProcessingConfig(
            ts_id="http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-swin_30min_raw",
            config_id="http://fdri.ceh.ac.uk/id/data-processing-configuration/cosmos-bunny-swin_30min_raw-range",
            config_type=ConfigurationType.QUALITY_CONTROL,
            method_configs=[
                DataProcessingMethodConfig(
                    method="range",
                    params={"lt": -10.0, "gt": 1200.0},
                )
            ],
            annotations={},
        )

        assert result == expected

    def test_infill_processing_config(self) -> None:
        filename = TEST_DATA_API_VALID / "data_processing_configuration" / "cosmos_bunny_swin_30min_raw_infill.json"
        api_model = valid_parses(load_json_file, filename, DataProcessingConfiguration)

        result = map_processing_config_item(api_model.items[0], MagicMock())

        expected = DataProcessingConfig(
            ts_id="http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-swin_30min_raw",
            config_id="http://fdri.ceh.ac.uk/id/data-processing-configuration/cosmos-infill-cosmos-bunny-swin_30min_raw",
            config_type=ConfigurationType.INFILLING,
            method_configs=[
                DataProcessingMethodConfig(
                    method="linear_linear",
                    params={"max_gap_size": 6, "window": 1},
                    start_date=datetime(2013, 1, 1, 0, 30, 0),
                )
            ],
            annotations={"priority": 1},
        )

        assert result == expected

    def test_correction_processing_config(self) -> None:
        filename = TEST_DATA_API_VALID / "data_processing_configuration" / "cosmos_bunny_swin_30min_raw_correction.json"
        api_model = valid_parses(load_json_file, filename, DataProcessingConfiguration)

        result = map_processing_config_item(api_model.items[0], MagicMock())

        expected = DataProcessingConfig(
            ts_id="http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-swin_30min_raw",
            config_id="http://fdri.ceh.ac.uk/id/data-processing-configuration/sgb0ag444qc40u99nsdo8n5m0kuscic7",
            config_type=ConfigurationType.CORRECTION,
            method_configs=[
                DataProcessingMethodConfig(
                    method="scalar",
                    params={"correction_factor": 0.98787},
                    start_date=datetime(2020, 8, 10, 9, 30, 0),
                    end_date=datetime(2020, 8, 17, 15, 0, 0),
                )
            ],
            annotations={},
        )

        assert result == expected


class TestMapSiteMetadata:
    def test_simple_site_metadata(self) -> None:
        data = {
            "@id": "top_level_id",
            "easting": "1234.0",
            "northing": "5678.0",
            "lat": "0.1234",
            "long": "-0.5678",
            "altitude": 999,
            "operatingPeriod": {"@id": "operating_period_id", "startDate": "2000-01-01", "endDate": "2099-12-31"},
            "utilisedBy": [{"@id": "utilised_by_id", "label": ["programme name"]}],
        }

        api_model = SiteItem.model_validate(data)
        result = map_site_metadata(api_model)

        expected = SiteMetadata(
            site_id="top_level_id",
            easting=1234.0,
            northing=5678.0,
            lat=0.1234,
            lon=-0.5678,
            altitude=999.0,
            start_date=datetime(2000, 1, 1),
            end_date=datetime(2099, 12, 31),
            network="utilised_by_id",
        )
        assert result == expected
