from dritimeseriesprocessor.deriving.process_derivations import DerivationProcessor
from testing.testing_utils.testing_helper import TestHelper


class TestDerivationProcessor(TestHelper):
    def test_derivation_processor(self) -> None:
        input_json_path = self.data_dir.joinpath("inputs", "derivation_processor", "input_ts_ids.json")
        input_ts_ids = self.load_ts_ids_from_json_file(input_json_path)

        expected_json_path = self.data_dir.joinpath("outputs", "derivation_processor", "expected_ts_ids.json")
        expected_ts_ids = self.load_ts_ids_from_json_file(expected_json_path)

        derivation_processor = DerivationProcessor(ts_ids=input_ts_ids)
        actual_ts_ids = derivation_processor.run()

        self.compare_ts_ids(expected_ts_ids=expected_ts_ids, actual_ts_ids=actual_ts_ids)
