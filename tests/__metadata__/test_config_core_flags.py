import unittest
from parameterized import parameterized
from pydantic import ValidationError

from dritimeseriesprocessor.__metadata__.config_core_flags import CoreFlag


class TestCoreFlag(unittest.TestCase):
    def test_valid_core_flag(self):
        """Test that a valid CoreFlag instance is created correctly."""
        core_flag = CoreFlag(name="Test flag", description="Tests the tests",
                           symbol="T", id=1)
        self.assertEqual(core_flag.name, "Test flag")
        self.assertEqual(core_flag.description, "Tests the tests")
        self.assertEqual(core_flag.symbol, "T")
        self.assertEqual(core_flag.id, 1)

    @parameterized.expand([
        1.7,
        9,
        21
    ])
    def test_bad_id(self, bad_id):
        with self.assertRaises(ValidationError):
            CoreFlag(name="Test flag", description="Tests the tests",
                     symbol="T", id=bad_id)
