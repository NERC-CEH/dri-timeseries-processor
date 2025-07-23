import datetime

from dritimeseriesprocessor.__main__ import TimeSeriesProcessor
from testing.testing_utils.testing_helper import TestHelper


class TestTimeSeriesProcessor(TestHelper):
    def test_initialisation(self) -> None:
        """Test query parameters are constructed correctly."""

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

    def test_get_user_timeseries_ids(self) -> None:
        expected_ts_ids = self.load_ts_ids_from_json_file(
            self.output_dir.joinpath("time_series_processor", "user_ts_ids_alic1_pe.json")
        )
        ts_processor = TimeSeriesProcessor(
            sites="alic1", columns="PE", periodicity="PT30M", end_date="2024-03-10", period="P2D", network="cosmos"
        )
        ts_processor.get_user_timeseries_ids()

        self.compare_ts_ids(expected_ts_ids = expected_ts_ids, actual_ts_ids = ts_processor.ts_ids)

    def test_get_processing_timeseries_ids(self) -> None:
        expected_ts_ids = self.load_ts_ids_from_json_file(
            self.output_dir.joinpath("time_series_processor", "processing_ts_ids_alic1_pe.json")
        )
        ts_processor = TimeSeriesProcessor(
            sites="alic1", columns="PE", periodicity="PT30M", end_date="2024-03-10", period="P2D", network="cosmos"
        )
        ts_processor.get_processing_timeseries_ids()

        self.compare_ts_ids(expected_ts_ids = expected_ts_ids, actual_ts_ids = ts_processor.ts_ids)

    def test_get_timeseries_ids(self) -> None:
        expected_ts_ids = self.load_ts_ids_from_json_file(
            self.output_dir.joinpath("time_series_processor", "ts_ids_alic1_pe_full.json")
        )
        ts_processor = TimeSeriesProcessor(
            sites="alic1", columns="PE", periodicity="PT30M", end_date="2024-03-10", period="P2D", network="cosmos"
        )
        ts_processor.get_timeseries_ids()

        self.compare_ts_ids(expected_ts_ids = expected_ts_ids, actual_ts_ids = ts_processor.ts_ids)
