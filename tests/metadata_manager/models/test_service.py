

import unittest
from unittest.mock import patch

from metadata_manager.models.schemas.derivations import Methodology, Measure, DerivationMetadata
from metadata_manager.models.service import load_nested_timeseries_derivations

class TestLoadNestedTimeseriesDerivations(unittest.TestCase):
	"""Test the load_nested_timeseries_derivations function."""

	@patch("metadata_manager.models.service.handle_derivation_response")
	def test_imeseries_definition_no_nesting(self, mock_handle_derivation_response):
		"""Timeseries definition only dependent on its own raw dataset."""
	
		timeseries_defs = [
			"http://fdri.ceh.ac.uk/ref/cosmos/time-series/cov_ux_uz_30min_processed",
		]
	
		extract_derivation_result_1 = {
			"methodology":
			{
				"method_type": "process",
				"inputs":
				["http://fdri.ceh.ac.uk/ref/cosmos/time-series/cov_ux_uz_30min_raw"]
			}
		}

		extract_derivation_result_2 = {
			"methodology":
			{
				"inputs":[]
			}
		}
		mock_handle_derivation_response.side_effect = [extract_derivation_result_1, extract_derivation_result_2]

		expected = {
			"http://fdri.ceh.ac.uk/ref/cosmos/time-series/cov_ux_uz_30min_processed":
			{
				"methodology":
				{
					"method_type": "process",
					"inputs": ["http://fdri.ceh.ac.uk/ref/cosmos/time-series/cov_ux_uz_30min_raw"]
				}
			},
			"http://fdri.ceh.ac.uk/ref/cosmos/time-series/cov_ux_uz_30min_raw":
				{
				"methodology":
				{
					"inputs":[]
				}
			}
		}
		result = load_nested_timeseries_derivations(timeseries_defs)

		assert result == expected

	@patch("metadata_manager.models.service.handle_derivation_response")
	def test_timeseries_definition_nested(self, mock_handle_derivation_response):
		"""Single timeseries definition dependent on other processed datasets"""
	
		timeseries_defs = [
			"http://fdri.ceh.ac.uk/ref/cosmos/time-series/rn_30min_processed",
		]

		extract_derivation_result_1  =  {
			"methodology":
			{
				"method_type": "calculate",
				"inputs":
				["http://fdri.ceh.ac.uk/ref/cosmos/time-series/swin_30min_processed"]
			}
		}

		extract_derivation_result_2 = {
			"methodology":
			{
				"method_type": "process",
				"inputs":["http://fdri.ceh.ac.uk/ref/cosmos/time-series/swin_30min_raw"]
			}
		}


		extract_derivation_result_3 = {
			"methodology":
			{
				"inputs":[]
			}
		}

		mock_handle_derivation_response.side_effect = [extract_derivation_result_1, extract_derivation_result_2, extract_derivation_result_3]

		expected = {
			"http://fdri.ceh.ac.uk/ref/cosmos/time-series/rn_30min_processed":
			{
				"methodology":
				{
					"method_type": "calculate",
					"inputs":
					["http://fdri.ceh.ac.uk/ref/cosmos/time-series/swin_30min_processed"]
				}
			},
			"http://fdri.ceh.ac.uk/ref/cosmos/time-series/swin_30min_processed":
			{
				"methodology":
				{
					"method_type": "process",
					"inputs":
					["http://fdri.ceh.ac.uk/ref/cosmos/time-series/swin_30min_raw"]
				}
			},
			"http://fdri.ceh.ac.uk/ref/cosmos/time-series/swin_30min_raw":
			{
				"methodology":
				{
					"inputs":[]
				}
			}
		}

		result = load_nested_timeseries_derivations(timeseries_defs)

		assert result == expected



