from dritimeseriesprocessor.deriving.aggregation_and_derivation_processor import AggregationAndDerivationProcessor
from testing.utils.timeseries_test_helper import TimeSeriesTestHelper


class TestAggregationAndDerivationProcessor:
    def test_derivation_pe_30min(self, ts_test_helper: TimeSeriesTestHelper) -> None:
        """
        Check the derived potential evaporation is calculated correctly, including the dependent derived net radiation
        data.
        """
        input_json_path = ts_test_helper.data_dir.joinpath(
            "inputs", "aggregation_and_derivation_processor", "input_ts_ids_pe_30min.json"
        )
        # The input test data contains data from 08/03/24 07:30 - 08:30 inclusive (PT30M)
        input_ts_ids = ts_test_helper.load_ts_ids_from_json_file(input_json_path)

        expected_json_path = ts_test_helper.data_dir.joinpath(
            "outputs", "aggregation_and_derivation_processor", "expected_ts_ids_pe_30min.json"
        )
        expected_ts_ids = ts_test_helper.load_ts_ids_from_json_file(expected_json_path)

        aggregation_and_derivation_processor = AggregationAndDerivationProcessor(ts_ids=input_ts_ids)
        actual_ts_ids = aggregation_and_derivation_processor.run()

        ts_test_helper.compare_ts_ids(expected_ts_ids=expected_ts_ids, actual_ts_ids=actual_ts_ids)

    def test_aggregation_ta_1day(self, ts_test_helper: TimeSeriesTestHelper) -> None:
        """Check simple aggregation for temperature at 1 day resolution is calculated correctly."""
        input_json_path = ts_test_helper.data_dir.joinpath(
            "inputs", "aggregation_and_derivation_processor", "input_ts_ids_ta_1day.json"
        )
        input_ts_ids = ts_test_helper.load_ts_ids_from_json_file(input_json_path)

        expected_json_path = ts_test_helper.data_dir.joinpath(
            "outputs", "aggregation_and_derivation_processor", "expected_ts_ids_ta_1day.json"
        )
        expected_ts_ids = ts_test_helper.load_ts_ids_from_json_file(expected_json_path)

        aggregation_and_derivation_processor = AggregationAndDerivationProcessor(ts_ids=input_ts_ids)
        actual_ts_ids = aggregation_and_derivation_processor.run()

        # Depending on the version of time_stream installed, metadata may not be transferred through to the aggregated
        # output. Therefore don't compare the metadata attribute for the time being.
        ts_test_helper.compare_ts_ids(
            expected_ts_ids=expected_ts_ids, actual_ts_ids=actual_ts_ids, attributes_to_ignore=["metadata"]
        )

    def test_aggregation_pe_1day(self, ts_test_helper: TimeSeriesTestHelper) -> None:
        """
        Check aggregation for potential evaporation at 1 day resolution is calculated correctly.

        This should involve calling both the derivation calculations to produce the net radiation and 30min potential
        evaporation data, and the aggregation calculation to produce 1 day potential evaporation data.

        """
        input_json_path = ts_test_helper.data_dir.joinpath(
            "inputs", "aggregation_and_derivation_processor", "input_ts_ids_pe_1day.json"
        )
        input_ts_ids = ts_test_helper.load_ts_ids_from_json_file(input_json_path)

        expected_json_path = ts_test_helper.data_dir.joinpath(
            "outputs", "aggregation_and_derivation_processor", "expected_ts_ids_pe_1day.json"
        )
        expected_ts_ids = ts_test_helper.load_ts_ids_from_json_file(expected_json_path)

        aggregation_and_derivation_processor = AggregationAndDerivationProcessor(ts_ids=input_ts_ids)
        actual_ts_ids = aggregation_and_derivation_processor.run()

        # Depending on the version of time_stream installed, metadata may not be transferred through to the aggregated
        # output. Therefore don't compare the metadata attribute for the time being.
        ts_test_helper.compare_ts_ids(
            expected_ts_ids=expected_ts_ids, actual_ts_ids=actual_ts_ids, attributes_to_ignore=["metadata"]
        )

    def test_aggregation_precip_1min(self, ts_test_helper: TimeSeriesTestHelper) -> None:
        """
        Check aggregation for precip at 1 min resolution is calculated correctly

        This should involve updating the column name in the aggregated timeseries

        """
        input_json_path = ts_test_helper.data_dir.joinpath(
            "inputs", "aggregation_and_derivation_processor", "input_ts_ids_precip_1min.json"
        )
        input_ts_ids = ts_test_helper.load_ts_ids_from_json_file(input_json_path)

        expected_json_path = ts_test_helper.data_dir.joinpath(
            "outputs", "aggregation_and_derivation_processor", "expected_ts_ids_pe_1day.json"
        )
        expected_ts_ids = ts_test_helper.load_ts_ids_from_json_file(expected_json_path)

        aggregation_and_derivation_processor = AggregationAndDerivationProcessor(ts_ids=input_ts_ids)
        actual_ts_ids = aggregation_and_derivation_processor.run()

        # Depending on the version of time_stream installed, metadata may not be transferred through to the aggregated
        # output. Therefore don't compare the metadata attribute for the time being.
        ts_test_helper.compare_ts_ids(
            expected_ts_ids=expected_ts_ids, actual_ts_ids=actual_ts_ids, attributes_to_ignore=["metadata"]
        )