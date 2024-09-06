import unittest
from pathlib import Path
from databuilder import methods
from tempfile import TemporaryDirectory
import os

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

        methods._create_directory(output, purge=False)

        self.assertTrue(output.exists())

    def test_creation_of_existing_dir_no_purge(self):

        output = Path(self.dest.name) / "out-data"
        os.makedirs(output)
        test_file = output / "test.txt"

        with open(test_file, "w") as f:
            f.write("test text")

        self.assertTrue(test_file.exists())

        expected_content = os.listdir(output)

        methods._create_directory(output, purge=False)

        self.assertEqual(expected_content, os.listdir(output))

    def test_creation_of_existing_dir_with_purge(self):

        output = Path(self.dest.name) / "out-data"
        os.makedirs(output)
        test_file = output / "test.txt"

        with open(test_file, "w") as f:
            f.write("test text")

        self.assertListEqual(os.listdir(output), [test_file.parts[-1]])

        methods._create_directory(output, purge=True)
    

        self.assertListEqual(os.listdir(output), [])

    def test_data_copied_to_directory(self):

        output = Path(self.dest.name) / "out-data"
        methods._create_directory(output)

        methods._copy_files(output, src=self.cosmos_data)

        self.assertTrue(os.listdir(output), os.listdir(self.cosmos_data))
    
    def test_data_copied_to_directory_default_value(self):

        output = Path(self.dest.name) / "out-data"
        methods._create_directory(output)

        methods._copy_files(output)

        self.assertTrue(os.listdir(output), os.listdir(self.cosmos_data))