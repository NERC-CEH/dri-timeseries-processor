import pytest
from pydantic import ValidationError

from metadata_manager.models.schemas.datasets import (
    Meta,
    TimeSeriesDataset,
    TimeseriesDatasetResponse,
    TimeSeriesType,
)

VALID_META = {
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

VALID_ITEM = {
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


VALID_ITEM_WITH_METHODOLOGY = {
    "@id": "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-pe_30min_processed",
    "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/TimeSeriesDataset"}],
    "type": [
        {
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
    ],
    "sourceBucket": "ukceh-fdri-staging-timeseries-processed",
    "sourceDataset": "PROCESSED_DATA_30MIN",
    "sourceColumnName": "PE",
    "originatingSite": [{"@id": "http://fdri.ceh.ac.uk/id/site/cosmos-alic1"}],
}


class TestTimeSeriesDataset:
    """Test the TimeSeriesDataset model."""

    def test_valid_time_series_dataset(self) -> None:
        """Test creating valid TimeSeriesDataset instance."""
        dataset = TimeSeriesDataset.model_validate(VALID_ITEM.copy())
        assert dataset.id == VALID_ITEM["@id"]
        assert len(dataset.type_ref) == 1
        assert len(dataset.type) == 1
        assert len(dataset.originating_site) == 1
        assert dataset.source_bucket == VALID_ITEM["sourceBucket"]
        assert dataset.source_dataset == VALID_ITEM["sourceDataset"]
        assert dataset.source_column_name == VALID_ITEM["sourceColumnName"]
        assert len(dataset.originating_facility) == 1

    def test_valid_time_series_dataset_with_methodology(
        self,
    ) -> None:
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

        dataset = TimeSeriesDataset.model_validate(VALID_ITEM_WITH_METHODOLOGY.copy())

        assert dataset.id, VALID_ITEM_WITH_METHODOLOGY["@id"]
        assert len(dataset.type_ref) == 1
        assert len(dataset.type) == 1
        assert len(dataset.originating_site) == 1
        assert dataset.source_bucket == VALID_ITEM_WITH_METHODOLOGY["sourceBucket"]
        assert dataset.source_dataset == VALID_ITEM_WITH_METHODOLOGY["sourceDataset"]
        assert dataset.source_column_name == VALID_ITEM_WITH_METHODOLOGY["sourceColumnName"]

        dataset_type = dataset.type[0]
        assert isinstance(dataset_type, TimeSeriesType)
        assert dataset_type.model_dump() == expected_dataset_type_data

    @pytest.mark.parametrize(
        "data",
        [
            ("test_missing_type_ref", {k: v for k, v in VALID_ITEM.items() if k != "@type"}),
            ("test_missing_originating_site", {k: v for k, v in VALID_ITEM.items() if k != "originatingSite"}),
        ],
        ids=["test missing type ref", "test missing originating site"],
    )
    def test_invalid_time_series_dataset_field(self, data: dict) -> None:
        """Test validation fails for invalid TimeSeriesDataset fields."""
        with pytest.raises(ValidationError):
            TimeSeriesDataset.model_validate(data)


class TestMeta:
    """Test the Meta model."""

    def test_valid_meta(self) -> None:
        """Test creating valid Meta instance."""

        meta = Meta.model_validate(VALID_META)
        assert meta.id == VALID_META["@id"]
        assert meta.publisher == VALID_META["publisher"]
        assert meta.license == VALID_META["license"]
        assert meta.license_name == VALID_META["licenseName"]
        assert meta.comment == VALID_META["comment"]
        assert meta.version == VALID_META["version"]
        assert meta.has_format == VALID_META["hasFormat"]
        assert meta.limit == VALID_META["limit"]

    @pytest.mark.parametrize(
        "data", [({k: v for k, v in VALID_ITEM.items() if k != "publisher"})], ids=["test missing publisher"]
    )
    def test_invalid_meta_field(self, data: dict) -> None:
        """Test validation fails for invalid Meta fields."""
        with pytest.raises(ValidationError):
            Meta.model_validate(data)


class TestTimeseriesDatasetResponse:
    """Test the TimeseriesDatasetResponse model."""

    def test_valid_timeseries_dataset_response(self) -> None:
        """Test creating valid TimeseriesDatasetResponse instance."""
        valid_data = {"meta": VALID_META, "items": [VALID_ITEM]}

        response = TimeseriesDatasetResponse.model_validate(valid_data)
        assert response.meta.id == VALID_META["@id"]
        assert len(response.items) == 1
        assert response.items[0].id == VALID_ITEM["@id"]
