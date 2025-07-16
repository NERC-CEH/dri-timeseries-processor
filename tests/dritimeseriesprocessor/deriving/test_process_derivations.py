from typing import Dict, Union

import pytest
from time_stream import TimeSeries

from dritimeseriesprocessor.deriving.process_derivations import process_derivations


@pytest.fixture
def ts_ids()-> Dict[str, Dict[str, Union[str, TimeSeries]]]:
    return {
        "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-pe_30min_processed": {
            "ts_def": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/pe_30min_processed",
            "resolution": "PT30M",
            "periodicity": "PT30M",
            "processing_level": "processed",
            "sourceBucket": "ukceh-fdri-staging-timeseries-qc",
            "sourceDataset": "PROCESSED_DATA_30MIN",
            "sourceColumnName": "PE",
            "sourceSite": "ALIC1",
            "method_type": "calculate",
            "method": "calculate-calculate_pe",
            "inputs": [
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/rn_30min_processed",
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ws_30min_processed",
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_processed",
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/rh_30min_processed",
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/pa_30min_processed",
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/g2_30min_processed",
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/g1_30min_processed",
            ],
            "load": False,
        }
    }


@pytest.fixture
def input_ts_ids() -> Dict[str, Dict[str, Union[str, TimeSeries]]]:
    return {
        {
            "ts_def": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/rn_30min_processed",
            "resolution": "PT30M",
            "periodicity": "PT30M",
            "processing_level": "processed",
            "sourceBucket": "ukceh-fdri-staging-timeseries-qc",
            "sourceDataset": "PROCESSED_DATA_30MIN",
            "sourceColumnName": "RN",
            "sourceSite": "ALIC1",
            "method_type": "calculate",
            "method": "calculate-calculate_rn",
            "inputs": [
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/swin_30min_processed",
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/lwin_30min_processed",
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/swout_30min_processed",
                "http://fdri.ceh.ac.uk/ref/cosmos/time-series/lwout_30min_processed",
            ],
            "data": [-68.181, 302.85, 116.2, 364.6],
            "load": False,
        },
        {
            "ts_def": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ws_30min_processed",
            "resolution": "PT30M",
            "periodicity": "PT30M",
            "processing_level": "processed",
            "sourceBucket": "ukceh-fdri-staging-timeseries-qc",
            "sourceDataset": "PROCESSED_DATA_30MIN",
            "sourceColumnName": "WS",
            "sourceSite": "ALIC1",
            "method_type": "process",
            "method": None,
            "inputs": ["http://fdri.ceh.ac.uk/ref/cosmos/time-series/ws_30min_raw"],
            "data": [2.89954, 3.204, 0.214, 2.048],
            "load": False,
        },
        {
            "ts_def": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_processed",
            "resolution": "PT30M",
            "periodicity": "PT30M",
            "processing_level": "processed",
            "sourceBucket": "ukceh-fdri-staging-timeseries-qc",
            "sourceDataset": "PROCESSED_DATA_30MIN",
            "sourceColumnName": "TA",
            "sourceSite": "ALIC1",
            "method_type": "process",
            "method": None,
            "inputs": ["http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_raw"],
            "data": [1.977, 19.62, -2.144, 20.54],
            "load": False,
        },
        {
            "ts_def": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/rh_30min_processed",
            "resolution": "PT30M",
            "periodicity": "PT30M",
            "processing_level": "processed",
            "sourceBucket": "ukceh-fdri-staging-timeseries-qc",
            "sourceDataset": "PROCESSED_DATA_30MIN",
            "sourceColumnName": "RH",
            "sourceSite": "ALIC1",
            "method_type": "process",
            "method": None,
            "inputs": ["http://fdri.ceh.ac.uk/ref/cosmos/time-series/rh_30min_raw"],
            "data": [72.5, 57.62, 95.6, 65.41],
            "load": False,
        },
        {
            "ts_def": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/pa_30min_processed",
            "resolution": "PT30M",
            "periodicity": "PT30M",
            "processing_level": "processed",
            "sourceBucket": "ukceh-fdri-staging-timeseries-qc",
            "sourceDataset": "PROCESSED_DATA_30MIN",
            "sourceColumnName": "PA",
            "sourceSite": "ALIC1",
            "method_type": "process",
            "method": None,
            "inputs": ["http://fdri.ceh.ac.uk/ref/cosmos/time-series/pa_30min_raw"],
            "load": False,
            "data": [1024., 1011.365, 1033.649, 1020.695],
        },
        {
            "ts_def": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/g2_30min_processed",
            "resolution": "PT30M",
            "periodicity": "PT30M",
            "processing_level": "processed",
            "sourceBucket": "ukceh-fdri-staging-timeseries-qc",
            "sourceDataset": "PROCESSED_DATA_30MIN",
            "sourceColumnName": "G2",
            "sourceSite": "ALIC1",
            "method_type": "process",
            "method": None,
            "inputs": ["http://fdri.ceh.ac.uk/ref/cosmos/time-series/g2_30min_raw"],
            "load": False,
        },
        {
            "ts_def": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/g1_30min_processed",
            "resolution": "PT30M",
            "periodicity": "PT30M",
            "processing_level": "processed",
            "sourceBucket": "ukceh-fdri-staging-timeseries-qc",
            "sourceDataset": "PROCESSED_DATA_30MIN",
            "sourceColumnName": "G1",
            "sourceSite": "ALIC1",
            "method_type": "process",
            "method": None,
            "inputs": ["http://fdri.ceh.ac.uk/ref/cosmos/time-series/g1_30min_raw"],
            "load": False,
        },
    }


class TestProcessDerivations:
    def test_process_derivations(self, ts_ids, input_ts_ids):

        pass
