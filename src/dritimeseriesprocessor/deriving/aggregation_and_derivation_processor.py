import logging
from functools import lru_cache
from typing import Any, Dict, Union

import polars as pl
import time_stream as ts

from dritimeseriesprocessor.deriving.derivations import derive
from metadata_manager.models.common import ComponentType
from metadata_manager.models.service import load_methods

logger = logging.getLogger(__name__)

TIME_COLUMN = "time"
DERIVATION_METHOD = "calculate"
AGGREGATION_METHOD = "aggregate"


@lru_cache(maxsize=1)
def get_derivation_methods() -> Dict:
    """Load the derivation methods and cache the results."""
    return load_methods(ComponentType.DERIVATION.value)


@lru_cache(maxsize=1)
def get_aggregation_methods() -> Dict:
    """Load the aggregation methods and cache the results."""
    return load_methods(ComponentType.AGGREGATION.value)


class AggregationAndDerivationProcessor:
    """Calculates aggregated and derived data for any relevant ts.TimeFrame."""

    def __init__(self, ts_ids: Dict[str, Dict[str, Union[str, ts.TimeFrame]]]):
        self.aggregation_methods = get_aggregation_methods()
        self.derivation_methods = get_derivation_methods()
        self.ts_ids = ts_ids

    def run(self) -> Dict[str, Dict[str, Union[str, ts.TimeFrame]]]:
        """
        The main run method for the AggregationAndDerivationProcessor class.

        Returns:
            Dict[str, Dict[str, Union[str, ts.TimeFrame]]]: Updated timeseries with derived data added if applicable.
        """
        for ts_id, ts_metadata in self.ts_ids.items():
            # Skip any time series which have already been calculated
            if ts_metadata.get("data"):
                continue

            # Skip any time series which don't need aggregation or derivation calculating
            if ts_metadata.get("method_type") not in (DERIVATION_METHOD, AGGREGATION_METHOD):
                continue

            self.calculate_derivation_or_aggregation_for_ts_id(ts_id, ts_metadata)

        return self.ts_ids

    def calculate_derivation_or_aggregation_for_ts_id(self, ts_id: str, ts_metadata: Dict[str, Any]) -> None:
        """
        If appropriate (i.e. the corresponding method for derivation or aggregation is indicated in the ts_metadata)
        create the derived or aggregated data for the provided time series.

        If no method has been provided in the timeseries metadata, or the method isn't appropriate, no calculations
        will take place. Effectively the timeseries will be skipped.

        Args:
            ts_id: ID of the time series to calculate derived or aggregated for.
            ts_metadata: Dictionary containing the metadata corresponding to the provided timeseries ID

        """
        ts_method = ts_metadata.get("method_type")
        if ts_method == DERIVATION_METHOD:
            self.calculate_derivation(ts_id, ts_metadata)

        if ts_method == AGGREGATION_METHOD:
            self.calculate_aggregation(ts_id, ts_metadata)

    def calculate_derivation(self, ts_id: str, ts_metadata: Dict[str, Union[str, ts.TimeFrame]]) -> None:
        """
        Recursively calculates any derived data for a time series. The list of ts_ids is updated in situ, allowing a
        single recursive loop to be used to ensure any dependent derived data is calculated prior to the final
        derivation calculation for the input ts_id.

        Args:
            ts_id (str): The ID of the time series to calculate derived data for.
            ts_metadata (Dict[str, Union[str, ts.TimeFrame]]): Dictionary containing the metadata for the provided
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
        for dependent_ts_id in ts_metadata["inputs"]:
            dependent_ts_metadata = self.ts_ids[dependent_ts_id]
            dependent_ts = self.get_ts_data(dependent_ts_id)

            if not dependent_ts:
                raise ValueError(
                    f"Unable to calculate derivation for {ts_id}. The required dependent {dependent_ts_id} "
                    "has no available data."
                )

            # If the time column hasn't been added to input_data, add it in so it's available in the final ts.TimeFrame
            # object used for calculation of the derivation. At this point also set the periodicity and resolution
            # values based on the input ts metadata.
            if TIME_COLUMN not in input_data.keys():
                input_data[TIME_COLUMN] = dependent_ts.df[dependent_ts.time_name]
                periodicity = dependent_ts_metadata["periodicity"]
                resolution = dependent_ts_metadata["resolution"]

            source_column_name = dependent_ts_metadata["sourceColumnName"]
            input_data[source_column_name] = dependent_ts.df[source_column_name]

        # Construct the input time series object from the input data columns
        input_tf = ts.TimeFrame(
            df=pl.from_dict(input_data), time_name=TIME_COLUMN, resolution=resolution, periodicity=periodicity
        ).with_metadata(
            {
                "site_id": ts_metadata["sourceSite"],
                "column_name": ts_metadata["sourceColumnName"],
                "processing_level": ts_metadata["processing_level"],
            }
        )

        # Pass in the column name mapping as kwargs
        kwargs = {column_name.lower(): column_name for column_name in (input_data.keys() - {TIME_COLUMN})}

        logger.debug(f"Calculating derivation for timeseries: {ts_id} using method: {derivation_method_name}")

        derived_tf = derive(
            input_tf=input_tf,
            calc=derivation_method,
            column_name=ts_metadata["sourceColumnName"],
            **kwargs,
        )

        self.ts_ids[ts_id]["data"] = derived_tf

    def calculate_aggregation(self, ts_id: str, ts_metadata: Dict[str, Union[str, ts.TimeFrame]]) -> None:
        """
        Recursively calculates any aggregated data for a time series. The list of ts ids is updated in situ, allowing
        a single recursive loop to be used to calculate any dependent aggregated or derived input data prior to the
        final aggregation calculation for the 'parent' ts_id.

        Args:
            ts_id: The ID of the time series to calculate aggregated data for.
            ts_metadata: Dictionary containing the metadata for the provided time series ID.

        Raises:
            ValueError: More than one input timeseries has been specified for aggregation.

        """
        aggregation_method_name = ts_metadata["method"]
        aggregation_method = self.aggregation_methods.get(aggregation_method_name)

        # There should only be a single input to be aggregated. Any aggregations with multiple inputs should be
        # calculated using the derivation processor
        if len(ts_metadata["inputs"]) > 1:
            raise ValueError(f"More than one input has been provided for aggregation for {ts_id}")

        input_ts_id = ts_metadata["inputs"][0]
        input_tf = self.get_ts_data(input_ts_id)

        if not input_tf:
            raise ValueError(
                f"Unable to calculate aggregation for {ts_id}. The required input {input_ts_id} has no available data."
            )

        aggregation_period = ts.Period.of_iso_duration(ts_metadata["periodicity"])

        aggregated_tf = input_tf.aggregate(
            aggregation_period=aggregation_period,
            aggregation_function=aggregation_method.function_name,
            columns=ts_metadata["sourceColumnName"],
        )

        self.ts_ids[ts_id]["data"] = aggregated_tf

    def get_ts_data(self, ts_id: str) -> ts.TimeFrame:
        """
        Get the ts.TimeFrame object for a timeseries id.

        If the timeseries doesn't have data available immediately, any applicable derivation or aggregation
        calculations will be run.

        Args:
            ts_id: ID of the time series to fetch data for

        Returns:
            ts.TimeFrame object containing data corresponding to the provided timeseries ID.

        """
        ts_metadata = self.ts_ids[ts_id]
        if not ts_metadata.get("data"):
            self.calculate_derivation_or_aggregation_for_ts_id(ts_id, ts_metadata)

        return self.ts_ids[ts_id].get("data")
