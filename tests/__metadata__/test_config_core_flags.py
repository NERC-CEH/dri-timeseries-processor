import unittest
from parameterized import parameterized
from pydantic import ValidationError

from dritimeseriesprocessor.__metadata__.config_core_flags import CoreFlag


class TestCoreFlag(unittest.TestCase):
    @parameterized.expand([
        ("Test flag", "Tests the tests", "T", 1),
        ("Test flag", "Tests the tests", "T", 2),
        ("Test flag", "Tests the tests", "T", 16),
        ("Test flag", "Tests the tests", "T", 128)
    ])
    def test_valid_core_flag(self, name, description, symbol, flag_id):
        """Test that a valid CoreFlag instance is created correctly.
        Also testing valid id's do not raise errors.

        """
        core_flag = CoreFlag(name=name, description=description,
                           symbol=symbol, id=flag_id)
        self.assertEqual(core_flag.name, name)
        self.assertEqual(core_flag.description, description)
        self.assertEqual(core_flag.symbol, symbol)
        self.assertEqual(core_flag.id, flag_id)

    @parameterized.expand([
        -2,
        0,
        21,
        6
    ])
    def test_bad_id(self, bad_id):
        with self.assertRaises(ValueError):
            CoreFlag(name="Test flag", description="Tests the tests",
                     symbol="T", id=bad_id)
