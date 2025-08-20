import datetime
from unittest import mock

from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.s3_crud.write import S3Writer
from dritimeseriesprocessor.time_series_processor import TimeSeriesProcessor
from metadata_manager.api_manager import MetadataAPIManager
from testing.utils.mock_metadata_api import MockMetadataAPI
from testing.utils.s3_test_helper import S3TestHelper
from testing.utils.timeseries_test_helper import TimeSeriesTestHelper



@mock.patch.object(MetadataAPIManager, "_make_api_call")
class TestTimeSeriesProcessor(S3TestHelper, TimeSeriesTestHelper):
    def test_initialisation(self, mock_api_manager: mock.MagicMock) -> None:
        """Test query parameters are constructed correctly."""
        mock_api_manager.side_effect = MockMetadataAPI(api_data=self.default_metadata_api_data)

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
        mock_api_manager.side_effect = MockMetadataAPI(api_data=self.default_metadata_api_data)

        expected_ts_ids = self.load_ts_ids_from_json_file(
            self.output_dir.joinpath("time_series_processor", "user_ts_ids_alic1_pe.json")
        )

        ts_processor = TimeSeriesProcessor(
            sites="alic1", columns="PE", periodicity="PT30M", end_date="2024-03-10", period="P2D", network="cosmos"
        )
        ts_processor._get_user_timeseries_ids()

        self.compare_ts_ids(expected_ts_ids=expected_ts_ids, actual_ts_ids=ts_processor.ts_ids)

    def test_get_processing_timeseries_ids(self, mock_api_manager: mock.MagicMock) -> None:
        mock_api_manager.side_effect = MockMetadataAPI(api_data=self.default_metadata_api_data)

        expected_ts_ids = self.load_ts_ids_from_json_file(
            self.output_dir.joinpath("time_series_processor", "processing_ts_ids_alic1_pe.json")
        )

        ts_processor = TimeSeriesProcessor(
            sites="alic1", columns="PE", periodicity="PT30M", end_date="2024-03-10", period="P2D", network="cosmos"
        )
        ts_processor._get_processing_timeseries_ids()

        self.compare_ts_ids(expected_ts_ids=expected_ts_ids, actual_ts_ids=ts_processor.ts_ids)

    def test_get_dependent_timeseries_metadata(self, mock_api_manager: mock.MagicMock) -> None:
        api_data = self.default_metadata_api_data | self.create_ts_dependency_api_data()
        mock_api_manager.side_effect = MockMetadataAPI(api_data=api_data)

        expected_ts_ids = self.load_ts_ids_from_json_file(
            self.output_dir.joinpath("time_series_processor", "dependent_and_user_ts_ids_alic1_pe.json")
        )

        ts_processor = TimeSeriesProcessor(
            sites="alic1", columns="PE", periodicity="PT30M", end_date="2024-03-10", period="P2D", network="cosmos"
        )
        # Some ts_ids need to already exist in order to search through them to find any dependent timeseries metadata
        # and to ensure that self.ts_ids is extended and not completely overwritten.
        # Therefore run _get_user_timeseries_ids() first to generate the initial self.ts_ids data.
        ts_processor._get_user_timeseries_ids()
        ts_processor._get_dependent_timeseries_ids()

        self.compare_ts_ids(expected_ts_ids=expected_ts_ids, actual_ts_ids=ts_processor.ts_ids)

    def test_collate_timeseries_id_metadata_to_process(self, mock_api_manager: mock.MagicMock) -> None:
        api_data = self.default_metadata_api_data | self.create_ts_dependency_api_data()
        mock_api_manager.side_effect = MockMetadataAPI(api_data=api_data)

        expected_ts_ids = self.load_ts_ids_from_json_file(
            self.output_dir.joinpath("time_series_processor", "ts_ids_alic1_pe_full.json")
        )

        ts_processor = TimeSeriesProcessor(
            sites="alic1", columns="PE", periodicity="PT30M", end_date="2024-03-10", period="P2D", network="cosmos"
        )
        ts_processor._collate_timeseries_id_metadata_to_process()

        self.compare_ts_ids(expected_ts_ids=expected_ts_ids, actual_ts_ids=ts_processor.ts_ids)

    def test_write_timeseries(self, mock_api_manager: mock.MagicMock) -> None:
        """Test data is correctly written to the processed bucket.
        
        There is no existing data for this test. The end to end test tests
        the write functionality when there is existing data.
        """
    
        mock_api_manager.side_effect = MockMetadataAPI(api_data=self.default_metadata_api_data)
        ts_processor = TimeSeriesProcessor(
            sites="alic1,bunny,chimn,morly",
            columns="RN,PA,TA",
            periodicity="PT30M,PT1M",
            end_date="2024-03-10",
            period="P2D",
            network="cosmos",
        )
        s3_bucket = app_config.processed_bucket
        s3_client = ts_processor.s3_client

        # We dont really care about any loading or processing so just using our own generated ts_ids object
        # The processed ts ids contain two different resolutions (PT30M and PT1M) each with two different
        # sites. Within each permutation of resolution and site are multiple columns.
        # This structure ensures all functionality tested.
        ts_ids = self.load_ts_ids_from_json_file(self.input_dir.joinpath("write", "processed_ts_ids.json"))
        writer = S3Writer(s3_client)
        ts_processor._write_timeseries(ts_ids, s3_bucket, "cosmos", writer)

        # To check the data:
        # 1) Check the number of items in the bucket matches the number of
        # expected items
        # 2) loop through the expected outputs and check they match the processor output
        self._check_expected_parquet_files_exist_in_bucket(self.output_dir.joinpath("write", "full_process"), s3_bucket)
