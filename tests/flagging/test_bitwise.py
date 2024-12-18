import unittest
from unittest.mock import patch
from parameterized import parameterized

from dritimeseriesprocessor.flagging.bitwise import BitwiseFlag, FlagManager, BitWiseValidator, create_flag_class


# Define some example flags for testing
class ExampleFlag(BitwiseFlag):
    FLAG_A = 1
    FLAG_B = 2
    FLAG_C = 4


class TestFlagManager(unittest.TestCase):
    def setUp(self):
        """Set up the FlagManager instance for testing.
        """
        self.manager = FlagManager(ExampleFlag)

    def test_add_flag(self):
        """Test that a flag can be added to the manager.
        """
        self.manager.add_flag(ExampleFlag.FLAG_A)
        self.assertTrue(self.manager.has_flag(ExampleFlag.FLAG_A))

    def test_remove_flag(self):
        """Test that a flag can be removed from the manager.
        """
        self.manager.add_flag(ExampleFlag.FLAG_A)
        self.manager.remove_flag(ExampleFlag.FLAG_A)
        self.assertFalse(self.manager.has_flag(ExampleFlag.FLAG_A))

    def test_has_flag(self):
        """Test that the manager correctly identifies if a flag is set.
        """
        self.manager.add_flag(ExampleFlag.FLAG_A)
        self.assertTrue(self.manager.has_flag(ExampleFlag.FLAG_A))
        self.assertFalse(self.manager.has_flag(ExampleFlag.FLAG_B))

    def test_combined_flags(self):
        """Test that multiple flags can be added and checked correctly.
        """
        self.manager.add_flag(ExampleFlag.FLAG_A)
        self.manager.add_flag(ExampleFlag.FLAG_B)
        self.assertTrue(self.manager.has_flag(ExampleFlag.FLAG_A))
        self.assertTrue(self.manager.has_flag(ExampleFlag.FLAG_B))
        self.assertFalse(self.manager.has_flag(ExampleFlag.FLAG_C))

    def test_from_value(self):
        """Test that flags can be created from an integer value.
        """
        flags = ExampleFlag.from_value(0)  # Should set no flags
        self.assertFalse(flags & ExampleFlag.FLAG_A)
        self.assertFalse(flags & ExampleFlag.FLAG_B)
        self.assertFalse(flags & ExampleFlag.FLAG_C)

        flags = ExampleFlag.from_value(1)  # Should set FLAG_A
        self.assertTrue(flags & ExampleFlag.FLAG_A)
        self.assertFalse(flags & ExampleFlag.FLAG_B)
        self.assertFalse(flags & ExampleFlag.FLAG_C)

        flags = ExampleFlag.from_value(4)  # Should set FLAG_C
        self.assertFalse(flags & ExampleFlag.FLAG_A)
        self.assertFalse(flags & ExampleFlag.FLAG_B)
        self.assertTrue(flags & ExampleFlag.FLAG_C)

        flags = ExampleFlag.from_value(3)  # Should set FLAG_A and FLAG_B
        self.assertTrue(flags & ExampleFlag.FLAG_A)
        self.assertTrue(flags & ExampleFlag.FLAG_B)
        self.assertFalse(flags & ExampleFlag.FLAG_C)

    @parameterized.expand([
        ("negative", -3),
        ("too_high", 9),
    ])
    def test_bad_from_value(self, name, flag_val):
        """Test that flags can be created from an integer value.
        """
        with self.assertRaises(ValueError):
            ExampleFlag.from_value(flag_val)


class TestBitWiseValidator(unittest.TestCase):
    """Suite to check validity of QC tests in codebase"""

    def setUp(self):
        self.good_flags = [
            1 << 0,
            1 << 1,
            1 << 2,
            1 << 3,
        ]

    @parameterized.expand([
        ("str_num", "3"),
        ("str_word", "bad_flag"),
        ("float", 3.4),
    ])
    def bad_flag_type(self, name, flag):
        """Check error is raised when non integer flag given"""
        with self.assertRaises(TypeError):
            BitWiseValidator._check_flag_type(flag)

    def test_unique_flags(self):
        """Ensures that all tests have unique IDs"""
        BitWiseValidator._flags_are_unique(self.good_flags)

    def test_not_unique_flags(self):
        """Check error is raised when there are duplicate flags"""
        non_unique_flags = [
            1 << 0,
            1 << 1,
            1 << 1,
            1 << 2,
        ]
        with self.assertRaises(ValueError):
            BitWiseValidator._flags_are_unique(non_unique_flags)

    def test_sequential_flags(self):
        """Ensures that all tests have sequential IDs"""
        BitWiseValidator._flags_are_sequential(self.good_flags)

    def test_not_sequential_flags(self):
        """Check error is raised when flags are not sequential"""
        wrong_order_flags = [
            1 << 0,
            1 << 1,
            1 << 3,
            1 << 2,
        ]
        with self.assertRaises(ValueError):
            BitWiseValidator._flags_are_sequential(wrong_order_flags)

        missing_sequential_flags = [
            1 << 0,
            1 << 1,
            1 << 2,
            1 << 4,
        ]
        with self.assertRaises(ValueError):
            BitWiseValidator._flags_are_sequential(missing_sequential_flags)

    def test_bitwise_flags(self):
        """Ensures that all test_flags are bitwise (2**n)"""
        BitWiseValidator._flags_are_bitwise(self.good_flags)

    @parameterized.expand([
        ("one_bad", [1, 2, 3]),
        ("all_bad", [3, 5, 7]),
        ("zero", [0, 1, 2]),
    ])
    def test_not_bitwise_flags(self, name, flags):
        """Check error is raised when flags are not sequential"""
        with self.assertRaises(ValueError):
            BitWiseValidator._flags_are_bitwise(flags)

    @patch("dritimeseriesprocessor.flagging.bitwise.BitWiseValidator._flags_are_sequential")
    @patch("dritimeseriesprocessor.flagging.bitwise.BitWiseValidator._flags_are_bitwise")
    @patch("dritimeseriesprocessor.flagging.bitwise.BitWiseValidator._flags_are_unique")
    def test_validation_methods_called(self, mock_ids_are_unique, mock_ids_are_bitwise, mock_ids_are_sequential):
        """Tests that all validation methods are called when main function invoked"""

        BitWiseValidator.validate(self.good_flags)
        assert mock_ids_are_unique.called
        assert mock_ids_are_bitwise.called
        assert mock_ids_are_sequential.called


class TestCreateFlagClass(unittest.TestCase):
    def test_valid_flags(self):
        """Test creating a valid BitwiseFlag class.
        """
        flag_dict = {
            'FLAG_A': 1,
            'FLAG_B': 2,
            'FLAG_C': 4
        }
        MyFlag = create_flag_class('MyFlag', flag_dict)
        self.assertTrue(issubclass(MyFlag, BitwiseFlag))
        self.assertEqual(MyFlag.FLAG_A.value, 1)
        self.assertEqual(MyFlag.FLAG_B.value, 2)
        self.assertEqual(MyFlag.FLAG_C.value, 4)

    @parameterized.expand([
        ("non_bitwise", {'FLAG_A': 1,'FLAG_B': 3, 'FLAG_C': 4}),
        ("zero", {'FLAG_A': 0,'FLAG_B': 2, 'FLAG_C': 4}),
        ("duplicate", {'FLAG_A': 1,'FLAG_B': 1, 'FLAG_C': 2}),
        ("non_sequential", {'FLAG_A': 1,'FLAG_B': 4, 'FLAG_C': 2}),
    ])
    def test_bad_flags(self, name, flag_dict):
        """Test creating a BitwiseFlag class with non-bitwise values."""
        with self.assertRaises(ValueError):
            create_flag_class('MyFlag', flag_dict)
