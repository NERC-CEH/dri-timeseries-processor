import unittest

from parameterized import parameterized
from pydantic import ValidationError

from metadata_manager.models.schemas.datasets import (
    Meta,
    TimeSeriesDataset,
    TimeseriesDatasetResponse,
    TimeSeriesType,
)

valid_meta = {
    "@id": "http://fdri.ceh.ac.uk/id/dataset?originatingSite=http%3A%2F%2Ffdri.ceh.ac.uk%2Fid%2Fsite%2Fcosmos-bunny&originatingSite=http%3A%2F%2Ffdri.ceh.ac.uk%2Fid%2Fsite%2Fcosmos-alic1&type.measure.aggregation.periodicity=PT30M&type.processingLevel=http%3A%2F%2Ffdri.ceh.ac.uk%2Fref%2Fcommon%2Fprocessing-level%2Fprocessed&_view=timeseries",
    "publisher": "UK Centre for Ecology & Hydrology",
    "license": "http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    "licenseName": "OGL 3",
    "comment": "",
    "version": "1.0.0",
    "hasFormat": [
        "http://fdri.ceh.ac.uk/id/dataset.ttl?_view=timeseries&originatingSite=http%3A%2F%2Ffdri.ceh.ac.uk%2Fid%2Fsite%2Fcosmos-bunny&originatingSite=http%3A%2F%2Ffdri.ceh.ac.uk%2Fid%2Fsite%2Fcosmos-alic1&type.measure.aggregation.periodicity=PT30M&type.processingLevel=http%3A%2F%2Ffdri.ceh.ac.uk%2Fref%2Fcommon%2Fprocessing-level%2Fprocessed",
        "http://fdri.ceh.ac.uk/id/dataset.geojson?_view=timeseries&originatingSite=http%3A%2F%2Ffdri.ceh.ac.uk%2Fid%2Fsite%2Fcosmos-bunny&originatingSite=http%3A%2F%2Ffdri.ceh.ac.uk%2Fid%2Fsite%2Fcosmos-alic1&type.measure.aggregation.periodicity=PT30M&type.processingLevel=http%3A%2F%2Ffdri.ceh.ac.uk%2Fref%2Fcommon%2Fprocessing-level%2Fprocessed",
        "http://fdri.ceh.ac.uk/id/dataset.html?_view=timeseries&originatingSite=http%3A%2F%2Ffdri.ceh.ac.uk%2Fid%2Fsite%2Fcosmos-bunny&originatingSite=http%3A%2F%2Ffdri.ceh.ac.uk%2Fid%2Fsite%2Fcosmos-alic1&type.measure.aggregation.periodicity=PT30M&type.processingLevel=http%3A%2F%2Ffdri.ceh.ac.uk%2Fref%2Fcommon%2Fprocessing-level%2Fprocessed",
        "http://fdri.ceh.ac.uk/id/dataset.json?_view=timeseries&originatingSite=http%3A%2F%2Ffdri.ceh.ac.uk%2Fid%2Fsite%2Fcosmos-bunny&originatingSite=http%3A%2F%2Ffdri.ceh.ac.uk%2Fid%2Fsite%2Fcosmos-alic1&type.measure.aggregation.periodicity=PT30M&type.processingLevel=http%3A%2F%2Ffdri.ceh.ac.uk%2Fref%2Fcommon%2Fprocessing-level%2Fprocessed",
        "http://fdri.ceh.ac.uk/id/dataset.rdf?_view=timeseries&originatingSite=http%3A%2F%2Ffdri.ceh.ac.uk%2Fid%2Fsite%2Fcosmos-bunny&originatingSite=http%3A%2F%2Ffdri.ceh.ac.uk%2Fid%2Fsite%2Fcosmos-alic1&type.measure.aggregation.periodicity=PT30M&type.processingLevel=http%3A%2F%2Ffdri.ceh.ac.uk%2Fref%2Fcommon%2Fprocessing-level%2Fprocessed",
        "http://fdri.ceh.ac.uk/id/dataset.csv?_view=timeseries&originatingSite=http%3A%2F%2Ffdri.ceh.ac.uk%2Fid%2Fsite%2Fcosmos-bunny&originatingSite=http%3A%2F%2Ffdri.ceh.ac.uk%2Fid%2Fsite%2Fcosmos-alic1&type.measure.aggregation.periodicity=PT30M&type.processingLevel=http%3A%2F%2Ffdri.ceh.ac.uk%2Fref%2Fcommon%2Fprocessing-level%2Fprocessed",
    ],
    "limit": 25,
}

valid_item = {
    "@id": "http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-lwout_30min_processed",
    "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/TimeSeriesDataset"}],
    "type": [
        {
            "@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/lwout_30min_processed",
            "processingLevel": {"@id": "http://fdri.ceh.ac.uk/ref/common/processing-level/processed"},
            "measure": {
                "@id": "http://fdri.ceh.ac.uk/ref/common/measure/lwout-wm-2-mean_prec-pt30m-pt30m",
                "variable": {
                    "@id": "http://fdri.ceh.ac.uk/ref/common/cop/lwout",
                    "prefLabel": ["Outgoing longwave radiation (corrected)"],
                },
                "hasUnit": {"@id": "http://fdri.ceh.ac.uk/ref/common/unit/wm-2", "prefLabel": ["Wm-2"]},
                "aggregation": {
                    "@id": "http://fdri.ceh.ac.uk/ref/common/aggregation/mean_prec-pt30m-pt30m",
                    "valueStatistic": {"@id": "http://fdri.ceh.ac.uk/ref/common/statistic/mean_prec"},
                    "periodicity": "PT30M",
                    "resolution": "PT30M",
                },
            },
        }
    ],
    "sourceBucket": "ukceh-fdri-staging-timeseries-processed",
    "sourceDataset": "PROCESSED_DATA_30MIN",
    "sourceColumnName": "LWOUT",
    "originatingFacility": [{"@id": "http://fdri.ceh.ac.uk/id/platform/cosmos-bunny-4cr"}],
    "originatingSite": [{"@id": "http://fdri.ceh.ac.uk/id/site/cosmos-bunny"}],
}

valid_item_with_methodology = {
    "@id": "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-pe_30min_processed",
    "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/TimeSeriesDataset"}],
    "type": [
        {
            "@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/pe_30min_processed",
            "processingLevel": {"@id": "http://fdri.ceh.ac.uk/ref/common/processing-level/processed"},
            "measure": {
                "@id": "http://fdri.ceh.ac.uk/ref/common/measure/pe-mm-total_prec-pt30m-pt30m",
                "variable": {"@id": "http://fdri.ceh.ac.uk/ref/common/cop/pe", "prefLabel": ["Potential Evaporation"]},
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
    ],
    "sourceBucket": "ukceh-fdri-staging-timeseries-processed",
    "sourceDataset": "PROCESSED_DATA_30MIN",
    "sourceColumnName": "PE",
    "originatingSite": [{"@id": "http://fdri.ceh.ac.uk/id/site/cosmos-alic1"}],
}


class TestTimeSeriesDataset(unittest.TestCase):
    """Test the TimeSeriesDataset model."""

    def setUp(self) -> None:
        self.valid_data = valid_item

    def test_valid_time_series_dataset(self) -> None:
        """Test creating valid TimeSeriesDataset instance."""
        dataset = TimeSeriesDataset.model_validate(self.valid_data)
        self.assertEqual(dataset.id, valid_item["@id"])
        self.assertEqual(len(dataset.type_ref), 1)
        self.assertEqual(len(dataset.type), 1)
        self.assertEqual(len(dataset.originating_site), 1)
        self.assertEqual(dataset.source_bucket, valid_item["sourceBucket"])
        self.assertEqual(dataset.source_dataset, valid_item["sourceDataset"])
        self.assertEqual(dataset.source_column_name, valid_item["sourceColumnName"])
        self.assertEqual(len(dataset.originating_facility), 1)

    def test_valid_time_series_dataset_with_methodology(self) -> None:
        """Test creating valid TimeSeriesDataset instance with methodology information present."""
        expected_dataset_type_data = {
            "id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/pe_30min_processed",
            "processing_level": {"id": "http://fdri.ceh.ac.uk/ref/common/processing-level/processed"},
            "measure": {
                "id": "http://fdri.ceh.ac.uk/ref/common/measure/pe-mm-total_prec-pt30m-pt30m",
                "variable": {"id": "http://fdri.ceh.ac.uk/ref/common/cop/pe", "pref_label": ["Potential Evaporation"]},
                "has_unit": {"id": "http://fdri.ceh.ac.uk/ref/common/unit/mm", "pref_label": ["mm"]},
                "aggregation": {
                    "id": "http://fdri.ceh.ac.uk/ref/common/aggregation/total_prec-pt30m-pt30m",
                    "value_statistic": {"id": "http://fdri.ceh.ac.uk/ref/common/statistic/total_prec"},
                    "periodicity": "PT30M",
                    "resolution": "PT30M",
                },
            },
            "methodology": {
                "id": "http://fdri.ceh.ac.uk/id/plan/cosmos-pe_30min_processed-derivation",
                "configuration_type": "http://fdri.ceh.ac.uk/ref/common/configuration-type/calculate",
                "method": "http://fdri.ceh.ac.uk/ref/common/method/calculate-calculate_pe",
                "uses": [
                    "http://fdri.ceh.ac.uk/ref/cosmos/time-series/rn_30min_processed",
                    "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ws_30min_processed",
                    "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_processed",
                    "http://fdri.ceh.ac.uk/ref/cosmos/time-series/rh_30min_processed",
                    "http://fdri.ceh.ac.uk/ref/cosmos/time-series/pa_30min_processed",
                    "http://fdri.ceh.ac.uk/ref/cosmos/time-series/g2_30min_processed",
                    "http://fdri.ceh.ac.uk/ref/cosmos/time-series/g1_30min_processed",
                ],
            },
        }

        dataset = TimeSeriesDataset.model_validate(valid_item_with_methodology)

        self.assertEqual(dataset.id, valid_item_with_methodology["@id"])
        self.assertEqual(len(dataset.type_ref), 1)
        self.assertEqual(len(dataset.type), 1)
        self.assertEqual(len(dataset.originating_site), 1)
        self.assertEqual(dataset.source_bucket, valid_item_with_methodology["sourceBucket"])
        self.assertEqual(dataset.source_dataset, valid_item_with_methodology["sourceDataset"])
        self.assertEqual(dataset.source_column_name, valid_item_with_methodology["sourceColumnName"])

        dataset_type = dataset.type[0]
        assert isinstance(dataset_type, TimeSeriesType)
        assert dataset_type.model_dump() == expected_dataset_type_data

    @parameterized.expand(
        [
            ("test_missing_type_ref", {k: v for k, v in valid_item.items() if k != "@type"}),
            ("test_missing_originating_site", {k: v for k, v in valid_item.items() if k != "originatingSite"}),
        ]
    )
    def test_invalid_time_series_dataset_field(self, _: None, data: dict) -> None:
        """Test validation fails for invalid TimeSeriesDataset fields."""
        with self.assertRaises(ValidationError):
            TimeSeriesDataset.model_validate(data)


class TestMeta(unittest.TestCase):
    """Test the Meta model."""

    def setUp(self) -> None:
        self.valid_data = valid_meta

    def test_valid_meta(self) -> None:
        """Test creating valid Meta instance."""

        meta = Meta.model_validate(self.valid_data)
        self.assertEqual(meta.id, valid_meta["@id"])
        self.assertEqual(meta.publisher, valid_meta["publisher"])
        self.assertEqual(meta.license, valid_meta["license"])
        self.assertEqual(meta.license_name, valid_meta["licenseName"])
        self.assertEqual(meta.comment, valid_meta["comment"])
        self.assertEqual(meta.version, valid_meta["version"])
        self.assertEqual(meta.has_format, valid_meta["hasFormat"])
        self.assertEqual(meta.limit, valid_meta["limit"])

    @parameterized.expand([("test_missing_publisher", {k: v for k, v in valid_item.items() if k != "publisher"})])
    def test_invalid_meta_field(self, _: None, data: dict) -> None:
        """Test validation fails for invalid Meta fields."""
        with self.assertRaises(ValidationError):
            Meta.model_validate(data)


class TestTimeseriesDatasetResponse(unittest.TestCase):
    """Test the TimeseriesDatasetResponse model."""

    def setUp(self) -> None:
        self.valid_data = {"meta": valid_meta, "items": [valid_item]}

    def test_valid_timeseries_dataset_response(self) -> None:
        """Test creating valid TimeseriesDatasetResponse instance."""
        response = TimeseriesDatasetResponse.model_validate(self.valid_data)
        self.assertEqual(response.meta.id, valid_meta["@id"])
        self.assertEqual(len(response.items), 1)
        self.assertEqual(response.items[0].id, valid_item["@id"])
