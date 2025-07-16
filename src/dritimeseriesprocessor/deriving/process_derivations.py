import logging
from functools import lru_cache
from typing import Dict, Union

import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.deriving.derivations import derive
from metadata_manager.models.methods.method_registry import MethodType
from metadata_manager.models.service import load_methods

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_derivation_methods() -> Dict:
    """Load the infill methods and cache the results."""
    return load_methods(MethodType.DERIVATION.value)


class DerivationProcessor:
    def __init__(self, ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]]):
        self.derivation_methods = get_derivation_methods()
        self.ts_ids = ts_ids

    def run(self) -> Dict[str, Dict[str, Union[str, TimeSeries]]]:
        for ts_id, ts_metadata in self.ts_ids.items():
            # Skip any time series which don't have a derivation method defined
            if ts_metadata.get("method_type") != "calculate":
                print(f"Skipping: {ts_id}") ## DEBUGGING - DELETE LATER
                continue

            # Skip any time series which have already been calculated
            if ts_metadata.get("data"):
                continue

            self.calculate_derivation(ts_id, ts_metadata)

        return self.ts_ids

    def calculate_derivation(self, ts_id: str, ts_metadata: Dict[str, Union[str, TimeSeries]]) -> None:
        derivation_method = self.derivation_methods[ts_metadata["method"]]

        input_ids = [convert_ts_def_to_ts_id(ts_def, ts_metadata["sourceSite"]) for ts_def in ts_metadata["inputs"]]
        inputs = {input_id: self.ts_ids[input_id] for input_id in input_ids}

        input_data = {}
        for input_ts_id, input_ts_metadata in inputs.items():
            if not input_ts_metadata.get("data") and input_ts_metadata.get("method_type") == "calculate":
                self.calculate_derivation(input_ts_id, input_ts_metadata)

            ts_data = self.ts_ids[input_ts_id].get("data")
            if not ts_data:
                raise ValueError(
                    f"Unable to process derivation for {ts_id}, required input {input_ts_id} has no available data."
                )

            input_data[input_ts_metadata['sourceColumnName']] = ts_data

        # Construct the input time series object from the input data columns
        ts = TimeSeries(
            df = pl.from_dict(input_data),
            time_name = "time",
            resolution = ts_metadata["resolution"],
            periodicity = ts_metadata["periodicity"],
            metadata={
                "site_id": ts_metadata["sourceSite"],
                "column_name": ts_metadata["sourceColumnName"],
                "processing_level": ts_metadata["processing_level"],
            },
        )

        derived_data = derive(
            ts = ts,
            calc = derivation_method,
            column_name = ts_metadata["sourceColumnName"],
        )

        self.ts_ids[ts_id]["data"] = derived_data


def convert_ts_def_to_ts_id(ts_def: str, site_id: str) -> str:
    return f"http://fdri.ceh.ac.uk/id/dataset/cosmos-{site_id.lower()}-{ts_def.split('/')[-1]}"
