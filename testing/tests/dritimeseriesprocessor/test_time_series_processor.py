import unittest
from unittest.mock import patch

from dritimeseriesprocessor.__main__ import TimeSeriesProcessor



class TestTimeSeriesProcessor:
    def test_initialisation(self) -> None:
        """Test query parameters are constructed correctly."""

        ts_processor = TimeSeriesProcessor(
            sites = ["alic1", "bunny"],

        )

        pass