import logging
from functools import lru_cache
from typing import Dict, Union

import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.deriving.derivations import derive
from dritimeseriesprocessor.utils import map_def_to_id
from metadata_manager.models.common import ComponentType
from metadata_manager.models.service import load_methods

logger = logging.getLogger(__name__)

TIME_COLUMN = "time"


@lru_cache(maxsize=1)
def get_derivation_methods() -> Dict:
    """Load the infill methods and cache the results."""
    return load_methods(ComponentType.DERIVATION.value)


class DerivationProcessor:
    def __init__(self, ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]]):
        self.derivation_methods = get_derivation_methods()
        self.ts_ids = ts_ids

    def run(self) -> Dict[str, Dict[str, Union[str, TimeSeries]]]:
        for ts_id, ts_metadata in self.ts_ids.items():
            # Skip any time series which don't have a derivation method defined
            if ts_metadata.get("method_type") != "calculate":
                print(f"Skipping: {ts_id}")  ## DEBUGGING - DELETE LATER
                continue

            # Skip any time series which have already been calculated
            if ts_metadata.get("data"):
                continue

            self.calculate_derivation(ts_id, ts_metadata)

        return self.ts_ids

    def calculate_derivation(self, ts_id: str, ts_metadata: Dict[str, Union[str, TimeSeries]]) -> None:
        derivation_method = self.derivation_methods[ts_metadata["method"]]

        input_data = {}
        for input_ts_id in ts_metadata["inputs"]:
            input_ts_metadata = self.ts_ids[input_ts_id]
            if not input_ts_metadata.get("data") and input_ts_metadata.get("method_type") == "calculate":
                self.calculate_derivation(input_ts_id, input_ts_metadata)

            ts = self.ts_ids[input_ts_id].get("data")
            if not ts:
                raise ValueError(
                    f"Unable to process derivation for {ts_id}, required input {input_ts_id} has no available data."
                )

            # If the time column hasn't been added to input_data, add it in so it's available in the final TimeSeries
            # object used for calculation the derivation
            if TIME_COLUMN not in input_data.keys():
                input_data[TIME_COLUMN] = ts.df[TIME_COLUMN]

            source_column_name = input_ts_metadata["sourceColumnName"]
            input_data[source_column_name] = ts.df[source_column_name]

        # Construct the input time series object from the input data columns
        ts = TimeSeries(
            df=pl.from_dict(input_data),
            time_name=TIME_COLUMN,
            resolution=ts_metadata["resolution"],
            periodicity=ts_metadata["periodicity"],
            metadata={
                "site_id": ts_metadata["sourceSite"],
                "column_name": ts_metadata["sourceColumnName"],
                "processing_level": ts_metadata["processing_level"],
            },
        )

        # Pass in the column name mapping as kwargs 
        kwargs = {column_name.lower(): column_name for column_name in (input_data.keys() - {"time"})}

        derived_data = derive(
            ts,
            derivation_method,
            ts_metadata["sourceColumnName"],
            **kwargs
        )

        self.ts_ids[ts_id]["data"] = derived_data
