import unittest
from unittest.mock import patch
from pathlib import Path
from databuilder import parquet
from tempfile import TemporaryDirectory
import os
import duckdb
from datetime import time

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


class TestTimeClearing(DataCase):

    def setUp(self):
        self.dest = TemporaryDirectory()
        self.test_data = Path(self.dest.name) / "out-data"
        parquet.initialse_directory(self.test_data)
        
        self.target = f"{self.test_data}/PRECIP_1MIN_2024_LOOPED/2024-01/2024-01-30.parquet"
        self.fmt = "%H:%M"
        self.query = f"SELECT * FROM READ_PARQUET('{self.target}') WHERE strftime('{self.fmt}', \"time\")"

    def tearDown(self):
        self.dest.cleanup()

    def test_time_filter_gt(self):
        """Tests that method removes values greater than or equal to a certain time"""

        tm = time(hour=11)
        strtime = tm.strftime(self.fmt)

        query_pre = self.query + f" > '{strtime}'"

        with duckdb.connect() as con:
            result = con.execute(query_pre).fetchdf()

        assert 0 not in result.shape

        parquet.filter_by_time(self.target, tm,  operator=">")

        query_post = self.query + f"<= '{strtime}'"
        with duckdb.connect() as con:
            result = con.execute(query_post).fetchdf()

        self.assertEqual(result.shape[0], 0)
    
    def test_time_filter_ge(self):
        assert False

    def test_time_filter_eq(self):
        assert False

    def test_time_filter_lt(self):
        assert False

    def test_time_filter_le(self):
        assert False
