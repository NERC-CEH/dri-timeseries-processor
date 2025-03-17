import unittest
from datetime import datetime
from parameterized import parameterized
from unittest.mock import patch, MagicMock

from metadata_manager.models.time_series import (
    Measure,
    ProcessingLevel,
    TimeSeriesMetadata,
    TimeSeriesMetadataResponse
)


class TestMeasure(unittest.TestCase):
    def test_extract_measure_info_with_units(self):
        """Test extraction of measure info with units present."""
        test_data = {
            "hasUnit": {
                "prefLabel": ["mm/day"]
            },
            "aggregation": {
                "resolution": "P1D",
                "periodicity": "P1Y"
            }
        }
        measure = Measure.model_validate(test_data)
        self.assertEqual(measure.units, "mm/day")
        self.assertEqual(measure.resolution, "P1D")
        self.assertEqual(measure.periodicity, "P1Y")

    def test_extract_measure_info_without_units(self):
        """Test extraction of measure info without units."""
        test_data = {
            "hasUnit": {},
            "aggregation": {
                "resolution": "P1D",
                "periodicity": "P1Y"
            }
        }
        measure = Measure.model_validate(test_data)

        self.assertIsNone(measure.units)
        self.assertEqual(measure.resolution, "P1D")
        self.assertEqual(measure.periodicity, "P1Y")

    def test_raises_measure_info_with_multiple_units(self):
        """Test extraction of measure info with multiple units."""
        test_data = {
            "hasUnit": {"prefLabel": ["mm", "mm-day"]},
            "aggregation": {
                "resolution": "P1D",
                "periodicity": "P1Y"
            }
        }
        with self.assertRaises(ValueError):
            measure = Measure.model_validate(test_data)

    def test_missing_aggregation_resolution(self):
        """Test validation fails when resolution field is missing."""
        test_data = {
            "hasUnit": {},
            "aggregation": {
                # Missing resolution
                "periodicity": "P1Y"
            }
        }

        with self.assertRaises(KeyError):
            Measure.model_validate(test_data)

    def test_missing_aggregation_periodicity(self):
        """Test validation fails when periodicity field is missing."""
        test_data = {
            "hasUnit": {},
            "aggregation": {
                "resolution": "P1D"
                # Missing periodicity
            }
        }

        with self.assertRaises(KeyError):
            Measure.model_validate(test_data)


class TestProcessingLevel(unittest.TestCase):
    def test_extract_processing_level_info(self):
        """Test extraction of processing level info."""
        test_data = {
            "prefLabel": ["Level 1"]
        }
        processing_level = ProcessingLevel.model_validate(test_data)
        self.assertEqual(processing_level.description, "Level 1")

    def test_multiple_processing_level_info_raises(self):
        """Test error raised when multiple processing level info found."""
        test_data = {
            "prefLabel": ["Level 1", "Level 2"]
        }
        with self.assertRaises(ValueError):
            ProcessingLevel.model_validate(test_data)

    def test_empty_preflabel(self):
        """Test validation with empty prefLabel."""
        test_data = {
            "prefLabel": []
        }
        with self.assertRaises(ValueError):
            ProcessingLevel.model_validate(test_data)

    def test_missing_preflabel(self):
        """Test validation fails when prefLabel is missing."""
        test_data = {}
        with self.assertRaises(KeyError):
            ProcessingLevel.model_validate(test_data)


class TestTimeSeriesMetadata(unittest.TestCase):
    def setUp(self):
        self.valid_data = {
            "@id": "http://example.com/timeseries/rainfall",
            "prefLabel": ["Daily Rainfall"],
            "measure": {
                "hasUnit": {
                    "prefLabel": ["mm"]
                },
                "aggregation": {
                    "resolution": "P1D",
                    "periodicity": "P1Y"
                }
            },
            "processingLevel": {
                "prefLabel": ["Level 1"]
            },
            "sourceBucket": "bucket-name",
            "sourceDataset": "rainfall-dataset",
            "sourceColumnName": "rainfall_1D"
        }

    def test_extract_timeseries_info(self):
        """Test extraction of time series metadata."""
        metadata = TimeSeriesMetadata.model_validate(self.valid_data)

        self.assertEqual(metadata.name, "rainfall")
        self.assertEqual(metadata.description, "Daily Rainfall")
        self.assertEqual(metadata.measure.units, "mm")
        self.assertEqual(metadata.measure.resolution, "P1D")
        self.assertEqual(metadata.processing_level.description, "Level 1")
        self.assertEqual(metadata.bucket, "bucket-name")
        self.assertEqual(metadata.dataset, "rainfall-dataset")
        self.assertEqual(metadata.column, "rainfall_1D")


    @parameterized.expand([
        ("test_missing_measure", "measure"),
        ("test_missing_processing_level", "processingLevel"),
        ("test_missing_bucket", "sourceBucket"),
        ("test_missing_dataset", "sourceDataset"),
        ("test_missing_column", "sourceColumnName"),
    ])
    def test_missing_required_fields(self, _, field):
        """Test validation fails when required fields are missing."""
        invalid_data = self.valid_data.copy()
        del invalid_data[field]
        with self.assertRaises(KeyError):
            TimeSeriesMetadata.model_validate(invalid_data)
