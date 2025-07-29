import datetime
from typing import Any, Dict
from unittest import mock

from dritimeseriesprocessor.time_series_processor import TimeSeriesProcessor
from metadata_manager.api_manager import MetadataAPIManager
from testing.utils.mock_metadata_api import MockMetadataAPI
from testing.utils.testing_helper import TestHelper, load_json


@mock.patch.object(MetadataAPIManager, "_make_api_call")
class TestTimeSeriesProcessor(TestHelper):
    def create_ts_dependency_api_data(self) -> Dict[str, Any]:
        base_url = "https://dri-metadata-api.staging.eds.ceh.ac.uk/id/dataset/cosmos-alic1-"
        ts_dependencies_dir = self.input_dir.joinpath("mock_metadata_api", "ts_dependencies_alic1")

        dependency_suffixes = [
            "pe_30min_processed",
            "rn_30min_processed",
            "swin_30min_processed",
            "lwout_30min_processed",
            "swout_30min_processed",
            "lwin_30min_processed",
            "pa_30min_processed",
            "g1_30min_processed",
            "g2_30min_processed",
            "rh_30min_processed",
            "ws_30min_processed",
            "ta_30min_processed",
            "tnr01c_30min_processed",
            "tnr01c_30min_raw",
            "battv_30min_raw",
            "scans_30min_raw",
            "swin_30min_raw",
            "lwout_30min_raw",
            "swout_30min_raw",
            "lwin_30min_raw",
            "pa_30min_raw",
            "g2_30min_raw",
            "rh_30min_raw",
            "ws_30min_raw",
            "ta_30min_raw",
            "g1_30min_raw",
        ]

        api_data = {}
        for dependency_suffix in dependency_suffixes:
            api_data[f"{base_url}{dependency_suffix}/_dependencies"] = load_json(
                ts_dependencies_dir.joinpath(f"{dependency_suffix}.json")
            )

        return api_data

    def test_initialisation(self, mock_api_manager: mock.MagicMock) -> None:
        """Test query parameters are constructed correctly."""
        mock_api_manager.side_effect = MockMetadataAPI(api_data=self.metadata_api_data)

        expected_site_query_parameter = sorted(
            [
                ("originatingSite", "http://fdri.ceh.ac.uk/id/site/cosmos-bunny"),
                ("originatingSite", "http://fdri.ceh.ac.uk/id/site/cosmos-alic1"),
            ]
        )
        expected_periodicity_query_parameter = [("type.measure.aggregation.periodicity", "PT30M")]
        expected_view_query_parameter = [("_view", "timeseries")]
        expected_start_date = datetime.date(2024, 3, 8)
        expected_end_date = datetime.date(2024, 3, 10)

        ts_processor = TimeSeriesProcessor(
            sites="alic1,bunny",
            columns="PE,PRECIP",
            periodicity="PT30M",
            end_date="2024-03-10",
            period="P2D",
            network="cosmos",
        )

        assert sorted(ts_processor.site_query_parameter) == sorted(expected_site_query_parameter)
        assert ts_processor.periodicity_query_parameter == expected_periodicity_query_parameter
        assert ts_processor.view_query_parameter == expected_view_query_parameter
        assert ts_processor.start_date == expected_start_date
        assert ts_processor.end_date == expected_end_date

    def test_get_user_timeseries_ids(self, mock_api_manager: mock.MagicMock) -> None:
        mock_api_manager.side_effect = MockMetadataAPI(api_data=self.metadata_api_data)

        expected_ts_ids = self.load_ts_ids_from_json_file(
            self.output_dir.joinpath("time_series_processor", "user_ts_ids_alic1_pe.json")
        )

        ts_processor = TimeSeriesProcessor(
            sites="alic1", columns="PE", periodicity="PT30M", end_date="2024-03-10", period="P2D", network="cosmos"
        )
        ts_processor._get_user_timeseries_ids()

        self.compare_ts_ids(expected_ts_ids=expected_ts_ids, actual_ts_ids=ts_processor.ts_ids)

    def test_get_processing_timeseries_ids(self, mock_api_manager: mock.MagicMock) -> None:
        mock_api_manager.side_effect = MockMetadataAPI(api_data=self.metadata_api_data)

        expected_ts_ids = self.load_ts_ids_from_json_file(
            self.output_dir.joinpath("time_series_processor", "processing_ts_ids_alic1_pe.json")
        )

        ts_processor = TimeSeriesProcessor(
            sites="alic1", columns="PE", periodicity="PT30M", end_date="2024-03-10", period="P2D", network="cosmos"
        )
        ts_processor._get_processing_timeseries_ids()

        self.compare_ts_ids(expected_ts_ids=expected_ts_ids, actual_ts_ids=ts_processor.ts_ids)

    def test_get_dependent_timeseries_metadata(self, mock_api_manager: mock.MagicMock) -> None:
        api_data = self.metadata_api_data | self.create_ts_dependency_api_data()
        mock_api_manager.side_effect = MockMetadataAPI(api_data=api_data)

        expected_ts_ids = self.load_ts_ids_from_json_file(
            self.output_dir.joinpath("time_series_processor", "dependent_and_user_ts_ids_alic1_pe.json")
        )

        ts_processor = TimeSeriesProcessor(
            sites="alic1", columns="PE", periodicity="PT30M", end_date="2024-03-10", period="P2D", network="cosmos"
        )
        # Some ts_ids need to already exist in order to search through them to find any dependent timeseries metadata
        # Therefore run _get_user_timeseries_ids() first
        ts_processor._get_user_timeseries_ids()
        ts_processor._get_dependent_timeseries_metadata()

        self.compare_ts_ids(expected_ts_ids=expected_ts_ids, actual_ts_ids=ts_processor.ts_ids)

    def test_collate_timeseries_id_metadata_to_process(self, mock_api_manager: mock.MagicMock) -> None:
        api_data = self.metadata_api_data | self.create_ts_dependency_api_data()
        mock_api_manager.side_effect = MockMetadataAPI(api_data=api_data)

        expected_ts_ids = self.load_ts_ids_from_json_file(
            self.output_dir.joinpath("time_series_processor", "ts_ids_alic1_pe_full.json")
        )

        ts_processor = TimeSeriesProcessor(
            sites="alic1", columns="PE", periodicity="PT30M", end_date="2024-03-10", period="P2D", network="cosmos"
        )
        ts_processor._collate_timeseries_id_metadata_to_process()

        self.compare_ts_ids(expected_ts_ids=expected_ts_ids, actual_ts_ids=ts_processor.ts_ids)
