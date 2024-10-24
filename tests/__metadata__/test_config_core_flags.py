import unittest
from parameterized import parameterized
from pydantic import ValidationError

from dritimeseriesprocessor.__metadata__.config_core_flags import CoreFlag


class TestCoreFlag(unittest.TestCase):
    def test_valid_core_flag(self):
        """Test that a valid CoreFlag instance is created correctly."""
        qc_test = CoreFlag(name="Test flag", description="Tests the tests",
                           symbol="T", id=1)
        self.assertEqual(qc_test.name, "Test flag")
        self.assertEqual(qc_test.description, "Tests the tests")
        self.assertEqual(qc_test.symbol, "T")
        self.assertEqual(qc_test.id, 1)

    @parameterized.expand([
        1.7,
        "2.1",
        None
    ])
    def test_bad_id(self, bad_id):
        with self.assertRaises(ValidationError):
            CoreFlag(name="Test flag", description="Tests the tests",
                    symbol="T", id=bad_id)