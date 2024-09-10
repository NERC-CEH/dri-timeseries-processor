import unittest
from unittest.mock import patch
from pathlib import Path
from databuilder import parquet
from databuilder.enums import Operator
from tempfile import TemporaryDirectory
import os
import duckdb
import datetime
from parameterized import  parameterized
import pandas as pd

class DataCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        cls.data_dir = Path(__file__).parents[2] / "parquet-data"
        cls.cosmos_data = cls.data_dir / "cosmos"
        cls.cosmos_precip = cls.cosmos_data / "PRECIP_1MIN_2024_LOOPED"
        cls.cosmos_soilmet = cls.cosmos_data / "SOILMET_30MIN_2024_LOOPED"

class TestInitialization(DataCase):

    def setUp(self):
        self.dest = TemporaryDirectory()
    
    def tearDown(self):
        self.dest.cleanup()

    def test_creation_from_nonexistance(self):

        output = Path(self.dest.name) / "out-data"

        self.assertFalse(output.exists())

        parquet._create_directory(output, purge=False)

        self.assertTrue(output.exists())

    def test_creation_of_existing_dir_no_purge(self):

        output = Path(self.dest.name) / "out-data"
        os.makedirs(output)
        test_file = output / "test.txt"

        with open(test_file, "w") as f:
            f.write("test text")

        self.assertTrue(test_file.exists())

        expected_content = os.listdir(output)

        parquet._create_directory(output, purge=False)

        self.assertEqual(expected_content, os.listdir(output))

    def test_creation_of_existing_dir_with_purge(self):

        output = Path(self.dest.name) / "out-data"
        os.makedirs(output)
        test_file = output / "test.txt"

        with open(test_file, "w") as f:
            f.write("test text")

        self.assertListEqual(os.listdir(output), [test_file.parts[-1]])

        parquet._create_directory(output, purge=True)
    

        self.assertListEqual(os.listdir(output), [])

    def test_data_copied_to_directory(self):

        output = Path(self.dest.name) / "out-data"
        parquet._create_directory(output)

        parquet._copy_files(output, src=self.cosmos_data)

        self.assertTrue(os.listdir(output), os.listdir(self.cosmos_data))
    
    def test_data_copied_to_directory_default_value(self):

        output = Path(self.dest.name) / "out-data"
        parquet._create_directory(output)

        parquet._copy_files(output)

        self.assertTrue(os.listdir(output), os.listdir(self.cosmos_data))

    @patch("databuilder.parquet._create_directory")
    @patch("databuilder.parquet._copy_files")
    def test_init_helper_method(self, copy_files, create_directory):
        """Tests that the helper method executes the expected private methods"""

        output = Path(self.dest.name) / "out-data"

        parquet.initialse_directory(output)

        self.assertTrue(copy_files.called)
        self.assertTrue(create_directory.called)

class TestParquetBuilderMethods(DataCase):
    def setUp(self):
        self.dest = TemporaryDirectory()
        self.test_data = Path(self.dest.name) / "out-data"
        parquet.initialse_directory(self.test_data)
        
        self.target = Path(f"{self.test_data}/PRECIP_1MIN_2024_LOOPED/2024-01/2024-01-30.parquet")
        
    def testDown(self):

        self.dest.cleanup()

    def test_class_instantiated(self):
        """Tests that the class is properly instantiated"""

        builder = parquet.ParquetBuilder(self.target)

        self.assertIsInstance(builder.target, Path)
        self.assertIsInstance(builder._output, Path)
        self.assertIsInstance(builder._dataframe, pd.DataFrame)

        self.assertEqual(builder.target, builder._output)
    
    def test_output_set(self):
        """Tests that the output parameter is set"""

        output = "/a/real/path"

        builder = parquet.ParquetBuilder(self.target, output)
        
        self.assertIsInstance(builder._output, Path)
        self.assertEqual(builder._output, Path(output))

    def test_error_if_target_not_found(self):
        """Test that an error is raised if the target file does not exist"""

        target = "/totally/not/a/real/path"

        with self.assertRaises(FileNotFoundError):
            parquet.ParquetBuilder(target)

    def test_reset(self):
        """Tests that the builder output can be reset"""

        builder = parquet.ParquetBuilder(self.target)

        self.assertIsNotNone(builder._dataframe)

        builder.reset()

        self.assertIsNone(builder._dataframe)

class TestTimeClearing(DataCase):

    def setUp(self):
        self.dest = TemporaryDirectory()
        self.test_data = Path(self.dest.name) / "out-data"
        parquet.initialse_directory(self.test_data)
        
        self.target = f"{self.test_data}/PRECIP_1MIN_2024_LOOPED/2024-01/2024-01-30.parquet"
        
        self.builder = parquet.ParquetBuilder(self.target)

    def tearDown(self):
        self.dest.cleanup()

    @parameterized.expand([1,1.2,">"])
    def test_error_if_non_enum_operator_used(self, operator):
        """Test that a TypeError is raised unless the operator is passed as an Operator enum"""

        tm = datetime.time(hour=11)

        with self.assertRaises(TypeError):
            self.builder.filter_by_time(tm, operator)
    
    @parameterized.expand([1,1.2,"10:20"])
    def test_error_if_non_datetime_received(self, time):
        """Test that a TypeError is raised unless the operator is passed as an Operator enum"""

        with self.assertRaises(TypeError):
            self.builder.filter_by_time(time, Operator.GREATER_THAN)


    def test_time_filter_gt(self):
        """Tests that method removes values not greater than the specified time"""

        tm = datetime.time(hour=11)
        operator = Operator.GREATER_THAN

        self.builder.filter_by_time(tm, operator)  
        self.assertNotEqual(self.builder._dataframe.size, 0)

        df = self.builder._dataframe.query(f"time.dt.time <= @pd.Timestamp('{tm}').time()")
        self.assertEqual(df.size, 0)

        df = self.builder._dataframe.query(f"time.dt.time {operator} @pd.Timestamp('{tm}').time()")
        self.assertNotEqual(df.size, 0)
    
    def test_time_filter_ge(self):
        """Tests that method removes values not greater than or equal to the specified time"""

        tm = datetime.time(hour=17, minute=14)
        operator = Operator.GREATER_THAN_EQUAL

        self.builder.filter_by_time(tm, operator)  
        self.assertNotEqual(self.builder._dataframe.size, 0)

        df = self.builder._dataframe.query(f"time.dt.time < @pd.Timestamp('{tm}').time()")
        self.assertEqual(df.size, 0)

        df = self.builder._dataframe.query(f"time.dt.time {operator} @pd.Timestamp('{tm}').time()")
        self.assertNotEqual(df.size, 0)

    def test_time_filter_eq(self):
        """Tests that method removes values not equal to the specified time"""

        tm = datetime.time(hour=17, minute=14)
        operator = Operator.EQUAL

        self.builder.filter_by_time(tm, operator)  
        self.assertNotEqual(self.builder._dataframe.size, 0)

        df = self.builder._dataframe.query(f"time.dt.time != @pd.Timestamp('{tm}').time()")
        self.assertEqual(df.size, 0)

        df = self.builder._dataframe.query(f"time.dt.time {operator} @pd.Timestamp('{tm}').time()")
        self.assertNotEqual(df.size, 0)

    def test_time_filter_lt(self):
        """Tests that method removes values not less than the specified time"""

        tm = datetime.time(hour=12, minute=14, second=36)
        operator = Operator.LESS_THAN

        self.builder.filter_by_time(tm, operator)  
        self.assertNotEqual(self.builder._dataframe.size, 0)

        df = self.builder._dataframe.query(f"time.dt.time >= @pd.Timestamp('{tm}').time()")
        self.assertEqual(df.size, 0)

        df = self.builder._dataframe.query(f"time.dt.time {operator} @pd.Timestamp('{tm}').time()")
        self.assertNotEqual(df.size, 0)

    def test_time_filter_le(self):
        """Tests that method removes values not less than or equal to the specified time"""

        tm = datetime.time(hour=23, minute=14, second=36)
        operator = Operator.LESS_THAN_EQUAL

        self.builder.filter_by_time(tm, operator)  
        self.assertNotEqual(self.builder._dataframe.size, 0)

        df = self.builder._dataframe.query(f"time.dt.time > @pd.Timestamp('{tm}').time()")
        self.assertEqual(df.size, 0)

        df = self.builder._dataframe.query(f"time.dt.time {operator} @pd.Timestamp('{tm}').time()")
        self.assertNotEqual(df.size, 0)

class TestPercentageRowRemoval(DataCase):

    def setUp(self):
        self.dest = TemporaryDirectory()
        self.test_data = Path(self.dest.name) / "out-data"
        parquet.initialse_directory(self.test_data)
        
        self.target = f"{self.test_data}/PRECIP_1MIN_2024_LOOPED/2024-01/2024-01-31.parquet"
        
        self.builder = parquet.ParquetBuilder(self.target)

    def tearDown(self):
        self.dest.cleanup()

    @parameterized.expand([-1, -1.2, 101, "1000"])
    def test_bad_percentage_error(self, percent):
        """Tests that an error is raised for bad percentage values"""

        with self.assertRaises(ValueError):
            self.builder.clear_percentage_of_rows(percent)

    @parameterized.expand([0, 10.5, 30, 75.9, 99.9, 100])
    def test_rows_removed(self, percent):
        
        size_before = self.builder._dataframe.shape[0]
        self.assertNotEqual(size_before, 0)

        acceptable_diff = size_before * 0.005
        expected = size_before * (1- (percent / 100))

        self.builder.clear_percentage_of_rows(percent)

        size_after = self.builder._dataframe.shape[0]

        self.assertAlmostEqual(size_after, expected, delta=acceptable_diff)

class TestPercentageCellRemoval(DataCase):

    def setUp(self):
        self.dest = TemporaryDirectory()
        self.test_data = Path(self.dest.name) / "out-data"
        parquet.initialse_directory(self.test_data)
        
        self.target = f"{self.test_data}/PRECIP_1MIN_2024_LOOPED/2024-01/2024-01-30.parquet"
        
        self.builder = parquet.ParquetBuilder(self.target)
        self.excluded_columns = ["time", "SITE_ID", "RECORD"]

    def tearDown(self):
        self.dest.cleanup()

    @parameterized.expand([-1, -1.2, 101, "1000"])
    def test_bad_percentage_error(self, percent):
        """Tests that an error is raised for bad percentage values"""

        with self.assertRaises(ValueError):
            self.builder.set_random_cells_to_null(percent)

    @parameterized.expand([0, 10.5, 30, 75.9, 99.9, 100])
    def test_cells_removed(self, percent):
        
        cols = [col for col in self.builder._dataframe.columns if col not in self.excluded_columns]
        
        size_before = self.builder._dataframe.shape[0]
        self.assertNotEqual(size_before, 0)

        expected = size_before * (percent/100)

        self.builder.set_random_cells_to_null(percent, exclude=self.excluded_columns)

        for col in cols:
            size_after = self.builder._dataframe[col].isna().sum()
            self.assertGreaterEqual(size_after, expected)