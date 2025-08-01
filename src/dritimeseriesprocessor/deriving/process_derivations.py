import logging
from functools import lru_cache
from typing import Dict, Union

import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor.deriving.derivations import derive
from metadata_manager.models.common import ComponentType
from metadata_manager.models.service import load_methods

logger = logging.getLogger(__name__)

TIME_COLUMN = "time"


@lru_cache(maxsize=1)
def get_derivation_methods() -> Dict:
    """Load the derivation methods and cache the results."""
    return load_methods(ComponentType.DERIVATION.value)


class DerivationProcessor:
    """Calculates derivation for any relevant TimeSeries."""

    def __init__(self, ts_ids: Dict[str, Dict[str, Union[str, TimeSeries]]]):
        self.derivation_methods = get_derivation_methods()
        self.ts_ids = ts_ids

    def run(self) -> Dict[str, Dict[str, Union[str, TimeSeries]]]:
        """
        The main run method for the DerivationProcessor class.

        Returns:
            Dict[str, Dict[str, Union[str, TimeSeries]]]: Updated timeseries with derived data added if applicable.
        """
        for ts_id, ts_metadata in self.ts_ids.items():
            # Skip any time series which don't have a derivation method defined
            if ts_metadata.get("method_type") != "calculate":
                continue

            # Skip any time series which have already been calculated
            if ts_metadata.get("data"):
                continue

            self.calculate_derivation(ts_id, ts_metadata)

        return self.ts_ids

    def calculate_derivation(self, ts_id: str, ts_metadata: Dict[str, Union[str, TimeSeries]]) -> None:
        """
        Recursively calculates any derived data for a time series. The list of ts_ids is updated in situ, allowing a
        single recursive loop to be used to ensure any dependent derived data is calculated prior to the final
        derivation calculation for the input ts_id.

        Args:
            ts_id (str): The ID of the time series to calculate derived data for.
            ts_metadata (Dict[str, Union[str, TimeSeries]]): Dictionary containing the metadata for the provided
                time series ID.

        Raises:
            ValueError: Could not find the appropriate derivation method.
            ValueError: One of the required inputs does not have any associated data.

        """

        derivation_method_name = ts_metadata["method"]
        derivation_method = self.derivation_methods.get(derivation_method_name)
        if not derivation_method:
            raise ValueError(
                f"Unable to process derivation for {ts_id}, the required derivation method: {derivation_method_name} "
                "could not be found."
            )

        input_data = {}
        periodicity = None
        resolution = None
        for input_ts_id in ts_metadata["inputs"]:
            input_ts_metadata = self.ts_ids[input_ts_id]
            if not input_ts_metadata.get("data") and input_ts_metadata.get("method_type") == "calculate":
                self.calculate_derivation(input_ts_id, input_ts_metadata)

            input_ts = self.ts_ids[input_ts_id].get("data")
            if not input_ts:
                raise ValueError(
                    f"Unable to process derivation for {ts_id}, required input {input_ts_id} has no available data."
                )

            # If the time column hasn't been added to input_data, add it in so it's available in the final TimeSeries
            # object used for calculation the derivation. At this point also set the periodicity and resolution values
            # based on the input ts metadata.
            if TIME_COLUMN not in input_data.keys():
                input_data[TIME_COLUMN] = input_ts.df[input_ts.time_name]
                periodicity = input_ts_metadata["periodicity"]
                resolution = input_ts_metadata["resolution"]

            source_column_name = input_ts_metadata["sourceColumnName"]
            input_data[source_column_name] = input_ts.df[source_column_name]

        # Construct the input time series object from the input data columns
        ts = TimeSeries(
            df=pl.from_dict(input_data),
            time_name=TIME_COLUMN,
            resolution=resolution,
            periodicity=periodicity,
            metadata={
                "site_id": ts_metadata["sourceSite"],
                "column_name": ts_metadata["sourceColumnName"],
                "processing_level": ts_metadata["processing_level"],
            },
        )

        # Pass in the column name mapping as kwargs
        kwargs = {column_name.lower(): column_name for column_name in (input_data.keys() - {TIME_COLUMN})}

        logger.debug(f"Calculating derivation for timeseries: {ts_id} using method: {derivation_method_name}")

        derived_data = derive(ts, derivation_method, ts_metadata["sourceColumnName"], **kwargs)

        self.ts_ids[ts_id]["data"] = derived_data
