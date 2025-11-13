import logging
import re
from collections import namedtuple
from datetime import datetime
from typing import Dict, List, Tuple

import boto3
from driutils.metadata_api.utils import URI_ID_EXTRACT_REGEX

from dritimeseriesprocessor import parser
from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.deriving.aggregation_and_derivation_processor import AggregationAndDerivationProcessor
from dritimeseriesprocessor.flagging.flagger import add_initial_core_flags
from dritimeseriesprocessor.logger import setup_logging
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.processor import load_data, process_timeseries
from dritimeseriesprocessor.s3_crud.write import S3Writer
from dritimeseriesprocessor.timeseries_container import TimeseriesContainer
from dritimeseriesprocessor.utils import call_method_async, map_def_to_id
from metadata_manager.models.common import (
    build_column_query_parameter,
    build_periodicity_query_parameter,
    build_processing_config_timeseries_id_query_parameter,
    build_processing_query_parameter,
    build_site_query_parameter,
    build_timeseries_id_query_parameter,
    build_view_query_parameter,
)
from metadata_manager.models.service import (
    load_config,
    load_datasets,
    load_dependent_datasets,
    load_sites,
)
from metadata_manager.transformers import (
    extract_dep_ts,
    extract_site_ids,
    extract_timeseries_id_metadata,
)

logger = logging.getLogger(__name__)
setup_logging()

metrics.setup_metrics()

UserTsID = namedtuple("UserTsID", ["site", "column", "periodicity"])

PROCESSING_CONFIG_DEP_TS_FUNCTIONS = {
    "correction": extract_dep_ts,
    "quality_control": extract_dep_ts,
    "infilling": extract_dep_ts,
}


class TimeSeriesProcessor:
    """Main class for processing time series data."""

    ts_ids: Dict[str, TimeseriesContainer]

    def __init__(
        self,
        network: str,
        period: str,
        user_ts_ids: List[str] = None,
        sites: str | None = None,
        columns: List[str] | None = None,
        periodicity: str | None = None,
        end_date: datetime = None,
    ):
        # Validate inputs as user_ts_ids is mutually exclusive to the combination of [sites, columns or periodicity]
        if user_ts_ids and (sites or columns or periodicity):
            raise ValueError(
                "Requesting a combination of specific timeseries ids and one or more of sites, columns and periodicies "
                "is not supported."
            )

        # Setup s3
        if app_config.environment == "local":
            self.s3_client = boto3.client("s3", endpoint_url=app_config.endpoint_url)
        else:
            self.s3_client = boto3.client("s3")

        self.network = network

        # Initialize the user parameters
        self.user_ts_ids = None
        self.sites = None
        self.columns = None
        self.periodicities = None

        if user_ts_ids:
            # Validate user specified timeseries ids and convert into UserTsID objects
            self.user_ts_ids = self._construct_user_ts_id_objects(user_ts_ids)
            self.sites = sorted(set(user_ts_id.site for user_ts_id in self.user_ts_ids))
        else:
            # Validate generic user arguments
            self.columns = parser.validate_columns(columns)
            self.periodicities = parser.validate_periodicity(periodicity)
            self.sites = self._validate_sites(sites)

        # Construct query parameters which are consistent across all metadata API calls
        self.site_query_parameter = build_site_query_parameter(sites=self.sites, network=self.network)
        self.view_query_parameter = build_view_query_parameter(view="timeseries")
        self.start_date, self.end_date = parser.build_date_range(period, end_date, app_config.environment)

        # Dictionary of ts_ids which will be filled during processing
        self.ts_ids = {}

    def run(self) -> None:
        """The main run function to process time series data.

        First collates metadata from the Metadata API for all user defined columns, any supporting processing time
        series (e.g. battery voltage), and any dependent time series data (e.g. processed precipitation is dependent
        on raw precipitation data).

        Then the initial processing is run before aggregated and derived data is calculated.

        Data is then written to s3.
        """
        # Collate metadata
        # ----------------
        logger.info("Collecting timeseries IDs")
        self._collate_timeseries_id_metadata_to_process()

        # Load data
        # ----------------
        logger.info("Loading raw data")
        self._load_raw_data()

        # Pre-aggregate or derive any RAW inputs where required
        # -----------------------------------------------------

        aggregation_and_derivation_processor = AggregationAndDerivationProcessor(self.ts_ids, processing_level="raw")
        self.ts_ids = aggregation_and_derivation_processor.run()

        # Process data
        # ------------
        logger.info("Processing data")
        self._process_data()

        logger.info("Calculating aggregated and derived data")
        aggregation_and_derivation_processor = AggregationAndDerivationProcessor(self.ts_ids)
        self.ts_ids = aggregation_and_derivation_processor.run()

        # Write data
        # ----------
        # TODO
        # Do we need to write out the processing columns?
        # Do we keep the extra aggregation columns?
        writer = S3Writer(self.s3_client)
        self._write_timeseries(self.ts_ids, app_config.processed_bucket, self.network, writer)

        # Record a successful run of the pipeline and push all metrics to the pushgateway
        metrics.record_successful_run()
        logger.info("Processing completed successfully")

        metrics.export_metrics_to_pushgateway(
            url=metrics.get_pushgateway_url(), job="timeseries-processor", registry=metrics.registry
        )

    def _collate_timeseries_id_metadata_to_process(self) -> None:
        """Collect all relevant time series metadata from the metadata API.

        This includes the processed timeseries defined by the user specified `columns` argument, any separate
        processing dependencies, and any dependent time series (e.g. the raw versions of any processed timeseries,
        any derivation / aggregation dependencies etc).

        """
        if self.user_ts_ids:
            self._get_specific_user_timeseries_ids()
        else:
            self._get_generic_user_timeseries_ids()

        if not self.ts_ids:
            raise ValueError("No time series IDs were found to be processed.")

        self._get_derived_dependent_ts_ids()

        # This should come last so we get dependencies for all ts_ids
        self._load_data_processing_configs()

        self._map_input_ts_defs_to_ts_ids()

    def _get_specific_user_timeseries_ids(self) -> None:
        """Collect the timeseries ID metadata for any specific ts-ids provided by the user.

        Each ts id to be fetched is defined by the parameters within a single UserTsID object. The combination
        of the site, column name and periodicity, alongside the configured network and an assumed processing level
        of 'processed' should point to a single timeseries ID. To avoid fetching any more timeseries than requested,
        each UserTsID object is processed separately, with the fetched data being appended to self.ts_ids.

        """
        processing_query_parameter = build_processing_query_parameter(level="processed")

        for user_ts_id in self.user_ts_ids:
            site_query_parameter = build_site_query_parameter(sites=[user_ts_id.site], network=self.network)
            column_query_parameter = build_column_query_parameter([user_ts_id.column])
            periodicity_query_parameter = build_periodicity_query_parameter([user_ts_id.periodicity])

            self._get_ts_id_metadata(
                site_query_parameter
                + periodicity_query_parameter
                + column_query_parameter
                + processing_query_parameter
                + self.view_query_parameter
            )

    def _get_generic_user_timeseries_ids(self) -> None:
        """Collect the timeseries id metadata for user specified processed variables.

        The metadata api service is queried for the timeseries id metadata for the processed variables requested by the
        user using the `columns` parameter, in combination with the requested site(s) and periodicities.

        The relevant response data is then extracted and added to the list of timeseries id metadata stored in
        self.ts_ids.

        """
        column_query_parameter = build_column_query_parameter(self.columns)
        periodicity_query_parameter = build_periodicity_query_parameter(self.periodicities)

        # For fetching the user specified timeseries id metadata, only the 'processed' ID data should be requested
        processing_query_parameter = build_processing_query_parameter(level="processed")

        self._get_ts_id_metadata(
            self.site_query_parameter
            + periodicity_query_parameter
            + column_query_parameter
            + processing_query_parameter
            + self.view_query_parameter
        )

    def _get_derived_dependent_ts_ids(self) -> None:
        """
        Recursively identify any time series derivation dependencies and fetch the corresponding metadata, adding the
        new time series id metadata entries into the main self.ts_ids dictionary.

        """
        dependent_timeseries_ids = self._identify_derived_dependent_ts_ids()

        # Fetch the corresponding timeseries metadata for the list of dependent time series IDs identified previously.
        timeseries_id_parameter = build_timeseries_id_query_parameter(dependent_timeseries_ids)

        self._get_ts_id_metadata(
            self.site_query_parameter + timeseries_id_parameter + self.view_query_parameter + [("_limit", 50)]
        )

    def _identify_derived_dependent_ts_ids(self) -> List[str]:
        """Build a list of the deriving dependencies for any existing ts_ids."""
        dependent_timeseries_ids = []
        for ts_id in self.ts_ids.keys():
            ts_name = re.match(URI_ID_EXTRACT_REGEX, ts_id).group(1)
            dependent_timeseries_list = load_dependent_datasets(ts_name)
            dependent_timeseries_ids.extend([dependent_ts.ts_id for dependent_ts in dependent_timeseries_list])

        return dependent_timeseries_ids

    def _load_data_processing_configs(self) -> None:
        raw_ts_ids = [ts_id for ts_id, ts_container in self.ts_ids.items() if ts_container.processing_level == "raw"]

        for raw_ts_id in raw_ts_ids:
            ts_id_query_parameter = build_processing_config_timeseries_id_query_parameter(raw_ts_id)

            self._load_data_processing_config(
                ts_ids_query_parameter=ts_id_query_parameter,
                config_type="correction",
                ts_container_attr="correction_configs",
            )

            self._load_data_processing_config(
                ts_ids_query_parameter=ts_id_query_parameter,
                config_type="quality_control",
                ts_container_attr="qc_configs",
            )

            self._load_data_processing_config(
                ts_ids_query_parameter=ts_id_query_parameter,
                config_type="infilling",
                ts_container_attr="infill_configs",
            )

    def _load_data_processing_config(
        self, ts_ids_query_parameter: List[Tuple], config_type: str, ts_container_attr: str
    ) -> None:
        configs = load_config(config_type, ts_ids_query_parameter)

        # Ensure all required TimeseriesContainer objects are available within self.ts_ids
        dependent_ts_ids = PROCESSING_CONFIG_DEP_TS_FUNCTIONS[config_type](configs)
        missing_ts_ids = [dep_ts for dep_ts in dependent_ts_ids if dep_ts not in self.ts_ids.keys()]
        if missing_ts_ids:
            timeseries_id_parameter = build_timeseries_id_query_parameter(missing_ts_ids)
            self._get_ts_id_metadata(self.site_query_parameter + timeseries_id_parameter + self.view_query_parameter)

        # Add the configurations to the relevant attribute within the appropriate TimeseriesContainer object
        for config in configs:
            getattr(self.ts_ids[config.ts_id], ts_container_attr).append(config)

    def _map_input_ts_defs_to_ts_ids(self) -> List[str]:
        """Convert any input ts_defs to ts_ids and update the corresponding ts_container."""
        for ts_id, ts_container in self.ts_ids.items():
            input_ts_ids = [
                map_def_to_id(input_def, ts_container.sourceSite, self.ts_ids) for input_def in ts_container.inputs
            ]

            # Update the list of inputs for the current timeseries to use ts_ids instead of ts_defs
            ts_container.inputs = input_ts_ids
            self.ts_ids[ts_id] = ts_container

    def _load_raw_data(self) -> None:
        """Load the raw data for each time series."""
        for ts_id, ts_container in self.ts_ids.items():
            if ts_container.load:
                logger.info(f"Loading data for {ts_id}")
                ts = load_data(ts_container, self.start_date, self.end_date)
                if not ts.df.is_empty():
                    ts = add_initial_core_flags(ts)

                    # Add the data into the ts_ids dict
                    self.ts_ids[ts_id].data = ts

    def _process_data(self) -> None:
        """Run the time series processing function.

        This is a wrapper function within which corrections, quality control and infilling are applied.

        """
        try:
            self.ts_ids = process_timeseries(self.ts_ids)
        except Exception as e:
            metrics.record_failed_run()
            logger.exception(f"An error occurred during processing: {str(e)}")
            metrics.export_metrics_to_pushgateway(
                url=metrics.get_pushgateway_url(), job="timeseries-processor", registry=metrics.registry
            )
            raise

    def _get_ts_id_metadata(self, query_parameters: List[Tuple[str, str]]) -> None:
        """
        Retrieve time series metadata from the metadata API and transform into the expected format, before updating
        the central dictionary of time series metadata.
        """
        response = load_datasets(query_parameters)
        ts_ids_metadata = extract_timeseries_id_metadata(response)

        self.ts_ids = self.ts_ids | ts_ids_metadata

    def _construct_user_ts_id_objects(self, user_ts_ids: List[List[str]]) -> None:
        """
        Convert the user provided list of [site, column, periodicity] to a named tuple, validating each parameter
        before storing the UserTsID objects in self.user_ts_ids.

        """
        validated_user_ts_ids = []

        for site, column, periodicity in user_ts_ids:
            validated_site = self._validate_sites(site)[0]
            validated_column = parser.validate_columns(column)[0]
            validated_periodicity = parser.validate_periodicity(periodicity)[0]

            validated_user_ts_ids.append(
                UserTsID(site=validated_site, column=validated_column, periodicity=validated_periodicity)
            )

        return validated_user_ts_ids

    def _validate_sites(self, sites: List[str] | str) -> List[str]:
        """Check that all provided site IDs can be found within the metadata API for the current network.

        Args:
            sites: Either a list of site ids, or a comma separated list of site ids to be validated.

        Returns:
            validated list of sites

        """
        metadata_sites = load_sites()
        metadata_sites = extract_site_ids(metadata_sites, network=self.network)

        return parser.validate_sites(sites, metadata_sites)

    @staticmethod
    def _write_timeseries(
        ts_ids: Dict[str, TimeseriesContainer], bucket_name: str, network: str, writer: S3Writer
    ) -> None:
        """Write the timeseries data to S3.

        Args:
            ts_ids: The processed timeseries ids
            bucket_name: The name of the S3 bucket.
            network: The name of the network
            writer: The S3 writer object.

        """
        # We only want to write data that has been processed, and we dont require
        # the ts id anymore
        processed_timeseries = [metadata for metadata in ts_ids.values() if metadata.processing_level == "processed"]

        # Structure the time series data ready for writing
        # Data combined by resolution and site, and then split into days
        data_to_write = writer.structure(processed_timeseries, bucket_name, network)

        # Write data to s3
        call_method_async(writer.write, data_to_write)
