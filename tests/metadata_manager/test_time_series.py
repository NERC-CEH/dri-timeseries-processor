import unittest
from parameterized import parameterized

from metadata_manager.models.time_series import (
    Measure,
    ProcessingLevel,
    TimeSeriesMetadata
)


class TestMeasure(unittest.TestCase):
    def test_extract_measure_info_with_units(self):
        """Test extraction of measure info with units present."""
        test_data = {
            "@id": "http://example.com/ref/common/measure/measure-id",
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
            "@id": "http://example.com/ref/common/measure/measure-id",
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
            "@id": "http://example.com/ref/common/measure/measure-id",
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
            "@id": "http://example.com/ref/common/measure/measure-id",
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
            "@id": "http://example.com/ref/common/measure/measure-id",
            "hasUnit": {},
            "aggregation": {
                "resolution": "P1D"
                # Missing periodicity
            }
        }

        with self.assertRaises(KeyError):
            Measure.model_validate(test_data)


class TestProcessingLevel(unittest.TestCase):
    def test_extract_processing_level_id(self):
        """Test extraction of processing level id."""
        test_data = {
            "@id": "http://example.com/ref/common/processing_level/proc-lev-id",
        }
        processing_level = ProcessingLevel.model_validate(test_data)
        self.assertEqual(processing_level.processing_level_id, "http://example.com/ref/common/processing_level/proc-lev-id")


class TestTimeSeriesMetadata(unittest.TestCase):
    def setUp(self):
        self.valid_data = {
            "@id": "http://example.com/timeseries/rainfall",
            "type": [
                {
                    "measure": {
                        "@id": "http://example.com/timeseries/rainfall-measure-id",
                        "hasUnit": {
                            "prefLabel": ["mm"]
                        },
                        "aggregation": {
                            "resolution": "P1D",
                            "periodicity": "P1Y"
                        }
                    },
                    "processingLevel": {
                        "@id": "http://example.com/common/proc-level-id",
                    },
                }
            ],
            "sourceBucket": "bucket-name",
            "sourceDataset": "rainfall-dataset",
            "sourceColumnName": "rainfall_1D"
        }

    def test_extract_timeseries_info(self):
        """Test extraction of time series metadata."""
        metadata = TimeSeriesMetadata.model_validate(self.valid_data)

        self.assertEqual(metadata.name, "rainfall")
        self.assertEqual(metadata.measure.measure_id, "http://example.com/timeseries/rainfall-measure-id")
        self.assertEqual(metadata.measure.units, "mm")
        self.assertEqual(metadata.measure.resolution, "P1D")
        self.assertEqual(metadata.measure.periodicity, "P1Y")
        self.assertEqual(metadata.processing_level.processing_level_id, "http://example.com/common/proc-level-id")
        self.assertEqual(metadata.bucket, "bucket-name")
        self.assertEqual(metadata.dataset, "rainfall-dataset")
        self.assertEqual(metadata.column, "rainfall_1D")


    @parameterized.expand([
        ("test_missing_type", "type"),
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
