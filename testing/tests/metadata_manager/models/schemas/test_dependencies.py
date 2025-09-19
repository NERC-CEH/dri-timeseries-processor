import unittest

from metadata_manager.models.schemas.dependencies import (
    DependentTimeSeriesMetadata,
    DependentTimeSeriesMetadataResponse,
    ProcessingLevel,
)


class TestProcessingLevel:
    def test_processing_level(self) -> None:
        data = {"@id": "http://fdri.ceh.ac.uk/ref/common/processing-level/processed"}
        processing_level = ProcessingLevel.model_validate(data)
        assert processing_level.processing_level_id == "http://fdri.ceh.ac.uk/ref/common/processing-level/processed"
        assert processing_level.processing_type == "processed"


class TestDependentTimeSeriesMetadataResponse:
    def test_dependent_time_series_metadata_response(self) -> None:
        data = {
            "meta": {
                "@id": "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-pe_30min_processed/_dependencies",
                "publisher": "UK Centre for Ecology & Hydrology",
                "license": "http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
                "licenseName": "OGL 3",
                "comment": "",
                "version": "1.0.0",
                "hasFormat": [
                    "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-pe_30min_processed/_dependencies.rdf",
                    "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-pe_30min_processed/_dependencies.html",
                    "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-pe_30min_processed/_dependencies.geojson",
                    "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-pe_30min_processed/_dependencies.json",
                    "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-pe_30min_processed/_dependencies.csv",
                    "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-pe_30min_processed/_dependencies.ttl",
                ],
            },
            "items": [
                {
                    "@id": "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-rn_30min_processed",
                    "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/TimeSeriesDataset"}],
                    "type": [
                        {
                            "@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/rn_30min_processed",
                            "processingLevel": {"@id": "http://fdri.ceh.ac.uk/ref/common/processing-level/processed"},
                            "measure": {
                                "@id": "http://fdri.ceh.ac.uk/ref/common/measure/rn-wm-2-mean_prec-pt30m-pt30m",
                                "variable": {
                                    "@id": "http://fdri.ceh.ac.uk/ref/common/cop/rn",
                                    "prefLabel": ["Net radiation"],
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
                    "sourceColumnName": "RN",
                    "originatingSite": [{"@id": "http://fdri.ceh.ac.uk/id/site/cosmos-alic1"}],
                },
            ],
        }

        expected_dependent_timeseries_metadata = DependentTimeSeriesMetadata(
            ts_id="http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-rn_30min_processed",
            name="cosmos-alic1-rn_30min_processed",
            processing_level_id="processed",
        )

        dependent_timeseries_metadata_response = DependentTimeSeriesMetadataResponse.model_validate(data)

        assert len(dependent_timeseries_metadata_response) == 1
        dependent_timeseries_metadata = dependent_timeseries_metadata_response[0]
        assert isinstance(dependent_timeseries_metadata, DependentTimeSeriesMetadata)

        assert expected_dependent_timeseries_metadata == dependent_timeseries_metadata
