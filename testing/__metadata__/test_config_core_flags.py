import pytest

from dritimeseriesprocessor.__metadata__.config_core_flags import CoreFlag


class TestCoreFlag:
    @pytest.mark.parametrize(
        "name,description,symbol,flag_id",
        [
            ("Test flag", "Tests the tests", "T", 1),
            ("Test flag", "Tests the tests", "T", 2),
            ("Test flag", "Tests the tests", "T", 16),
            ("Test flag", "Tests the tests", "T", 128),
        ],
    )
    def test_valid_core_flag(self, name: str, description: str, symbol: str, flag_id: int) -> None:
        """Test that a valid CoreFlag instance is created correctly.
        Also testing valid id's do not raise errors.

        """
        core_flag = CoreFlag(name=name, description=description, symbol=symbol, id=flag_id)
        assert core_flag.name == name
        assert core_flag.description == description
        assert core_flag.symbol == symbol
        assert core_flag.id == flag_id

    @pytest.mark.parametrize("bad_id", [-2, 0, 21, 6])
    def test_bad_id(self, bad_id: int) -> None:
        with pytest.raises(ValueError):
            CoreFlag(name="Test flag", description="Tests the tests", symbol="T", id=bad_id)
