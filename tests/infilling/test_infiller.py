import unittest
from unittest.mock import patch, MagicMock
import polars as pl
from polars.testing import assert_frame_equal
from datetime import datetime
from dritimeseriesprocessor.infilling.infiller import (
    run_infilling,
    get_infill_config,
    INFILL_METHODS
)



class TestRunInfilling(unittest.TestCase):
    """
    Test suite for the run_infilling function.
    """

    def setUp(self):
        """
        Set up common test data and mocks.
        """
        dates = pl.date_range(start=datetime(2023, 1, 1), end=datetime(2023, 1, 5), interval='1d', eager=True)

        self.test_df = pl.DataFrame({
            'time': dates,
            'temperature': [20.0, None, 22.0, None, 21.0],
            'humidity': [50, 55, None, None, 60]
        })

        self.mock_config = {
            'temperature': {
                'PT1M': MagicMock(methods=[
                    MagicMock(method_id='linear_interpolation', priority=1, constraints={'max_gap_size': 2})
                ])
            },
            'humidity': {
                'PT1M': MagicMock(methods=[
                    MagicMock(method_id='forward_fill', priority=1, constraints={'max_gap_size': 1})
                ])
            }
        }

        self.mock_infill_methods = {
            'linear_interpolation': MagicMock(return_value=pl.DataFrame({
                'value_filled': [None, 21.0, None, 21.5, None],
                'method_id': [None, 'INTERP_LINEAR', None, 'INTERP_LINEAR', None]
            })),
            'forward_fill': MagicMock(return_value=pl.DataFrame({
                'value_filled': [None, None, 55, 55, None],
                'method_id': [None, None, 'FORWARD_FILL', 'FORWARD_FILL', None]
            }))
        }

    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_config')
    @patch('dritimeseriesprocessor.infilling.infiller.INFILL_METHODS', new_callable=MagicMock)
    def test_run_infilling_basic(self, mock_infill_methods, mock_get_infill_config):
        """
        Test basic functionality of run_infilling.
        Checks if the function correctly applies infilling methods and updates the DataFrame.
        """
        mock_get_infill_config.return_value = self.mock_config
        mock_infill_methods.__getitem__.side_effect = self.mock_infill_methods.__getitem__

        result = run_infilling(self.test_df)

        self.assertIn('temperature_INFILL_METHOD', result.columns)
        self.assertIn('humidity_INFILL_METHOD', result.columns)
        self.assertEqual(result['temperature'].to_list(), [20.0, 21.0, 22.0, 21.5, 21.0])
        self.assertEqual(result['humidity'].to_list(), [50, 55, 55, 55, 60])

        mock_get_infill_config.assert_called_once_with("variables")
        self.mock_infill_methods['linear_interpolation'].assert_called_once()
        self.mock_infill_methods['forward_fill'].assert_called_once()

    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_config')
    @patch('dritimeseriesprocessor.infilling.infiller.INFILL_METHODS', new_callable=MagicMock)
    def test_run_infilling_no_config(self, mock_infill_methods, mock_get_infill_config):
        """
        Test run_infilling when no infill config is available for any column.
        Checks if the function returns the original DataFrame unchanged.
        """
        mock_get_infill_config.return_value = {}

        result = run_infilling(self.test_df)

        assert_frame_equal(result, self.test_df)
        mock_infill_methods.__getitem__.assert_not_called()

    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_config')
    @patch('dritimeseriesprocessor.infilling.infiller.INFILL_METHODS', new_callable=MagicMock)
    def test_run_infilling_no_methods(self, mock_infill_methods, mock_get_infill_config):
        """
        Test run_infilling when infill config exists but no methods are specified.
        Checks if the function returns the original DataFrame unchanged.
        """
        mock_config = {'temperature': {'PT1M': MagicMock(methods=[])}}
        mock_get_infill_config.return_value = mock_config

        result = run_infilling(self.test_df)

        assert_frame_equal(result, self.test_df)
        mock_infill_methods.__getitem__.assert_not_called()

    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_config')
    @patch('dritimeseriesprocessor.infilling.infiller.INFILL_METHODS', new_callable=MagicMock)
    def test_run_infilling_multiple_methods(self, mock_infill_methods, mock_get_infill_config):
        """
        Test run_infilling with multiple infill methods for a single column.
        Checks if the methods are applied in the correct order (by priority).
        """
        mock_config = {
            'temperature': {
                'PT1M': MagicMock(methods=[
                    MagicMock(method_id='linear_interpolation', priority=2, constraints={'max_gap': 2}),
                    MagicMock(method_id='forward_fill', priority=1, constraints={'max_gap': 1})
                ])
            }
        }
        mock_get_infill_config.return_value = mock_config
        mock_infill_methods.__getitem__.side_effect = self.mock_infill_methods.__getitem__

        result = run_infilling(self.test_df)

        self.mock_infill_methods['forward_fill'].assert_called_once()
        self.mock_infill_methods['linear_interpolation'].assert_called_once()
        self.assertEqual(
            list(mock_infill_methods.__getitem__.call_args_list),
            [unittest.mock.call('forward_fill'), unittest.mock.call('linear_interpolation')]
        )

    @patch('dritimeseriesprocessor.infilling.infiller.get_infill_config')
    @patch('dritimeseriesprocessor.infilling.infiller.INFILL_METHODS', new_callable=MagicMock)
    def test_run_infilling_default_resolution(self, mock_infill_methods, mock_get_infill_config):
        """
        Test run_infilling using default resolution when PT1M is not available.
        Checks if the function correctly falls back to the default resolution.
        """
        mock_config = {
            'temperature': {
                'default': MagicMock(methods=[
                    MagicMock(method_id='linear_interpolation', priority=1, constraints={'max_gap': 2})
                ])
            }
        }
        mock_get_infill_config.return_value = mock_config
        mock_infill_methods.__getitem__.side_effect = self.mock_infill_methods.__getitem__

        result = run_infilling(self.test_df)

        self.mock_infill_methods['linear_interpolation'].assert_called_once()
        self.assertIn('temperature_INFILL_METHOD', result.columns)
