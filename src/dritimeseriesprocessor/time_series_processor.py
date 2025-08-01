import logging
import re
from datetime import datetime
from typing import Dict, List, Tuple

import boto3

from dritimeseriesprocessor import parser
from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.deriving.process_derivations import DerivationProcessor
from dritimeseriesprocessor.flagging.flagger import add_initial_core_flags
from dritimeseriesprocessor.logger import setup_logging
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.processor import load_data, process_timeseries
from dritimeseriesprocessor.s3_crud.write import S3Writer
from dritimeseriesprocessor.utils import (
    group_by_date,
    merge_ts_def_metadata,
)
from metadata_manager.models.common import (
    URI_ID_EXTRACT_REGEX,
    build_column_query_parameter,
    build_periodicity_query_parameter,
    build_processing_query_parameter,
    build_site_query_parameter,
    build_timeseries_id_query_parameter,
    build_view_query_parameter,
)
from metadata_manager.models.service import (
    handle_derivation_response,
    load_datasets,
    load_dependent_datasets,
    load_sites,
)
from metadata_manager.transformers import extract_site_ids, extract_timeseries_id_metadata

logger = logging.getLogger(__name__)
setup_logging()

metrics.setup_metrics()

PROCESSING_COLUMNS = ["BATTV", "SCANS", "TNR01C"]


class TimeSeriesProcessor:
    """Main class for processing time series data."""

    def __init__(
        self,
        sites: str,
        columns: List[str],
        periodicity: str,
        end_date: datetime.date,
        period: str,
        network: str,
    ):
        # Setup s3
        if app_config.environment == "local":
            self.s3_client = boto3.client("s3", endpoint_url=app_config.endpoint_url)
        else:
            self.s3_client = boto3.client("s3")

        # Store arguments used for constructing more dynamic query parameters within the main run()
        self.columns = parser.validate_columns(columns)
        self.network = network

        # Construct query parameters which are consistent across all metadata API calls
        self.site_query_parameter = self._construct_site_query_parameter(sites=sites)
        self.periodicity_query_parameter = self._construct_periodicity_query_parameter(periodicity)
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

        """
        logger.info("Collecting timeseries IDs")
        self._collate_timeseries_id_metadata_to_process()

        logger.info("Loading raw data")
        self._load_raw_data()

        logger.info("Processing data")
        self._process_data()

        # TODO Aggregations here

        # Create derived data
        # -------------------
        logger.info("Calculating derived data")
        derivation_processor = DerivationProcessor(self.ts_ids)
        self.ts_ids = derivation_processor.run()

        # Writing
        # -------
        writer = S3Writer(self.s3_client)
        self._write_timeseries(self.ts_ids, app_config.processed_bucket, writer)

        metrics.record_successful_run()
        logger.info("Processing completed successfully")

        # Push all metrics at the end of successful processing
        metrics.export_metrics_to_pushgateway(
            url=metrics.get_pushgateway_url(), job="timeseries-processor", registry=metrics.registry
        )

    def _collate_timeseries_id_metadata_to_process(self) -> None:
        """Collect all relevant time series metadata from the metadata API.

        This includes the processed timeseries defined by the user specified `columns` argument, any separate
        processing dependencies, and any dependent time series (e.g. the raw versions of any processed timeseries,
        any derivation / aggregation dependencies etc).

        """
        self._get_user_timeseries_ids()
        self._get_processing_timeseries_ids()
        self._get_dependent_timeseries_ids()

        # Once the full list of timeseries ids has been collated, add any relevant derivation metadata to each
        # timeseries ID.
        self._add_derivation_metadata()

    def _get_user_timeseries_ids(self) -> None:
        """Collect the timeseries id metadata for user specified processed variables.

        The metadata api service is queried for the timeseries id metadata for the processed variables requested by the
        user using the `columns` parameter, in combination with the requested site(s) and periodicities.

        The relevant response data is then extracted and added to the list of timeseries id metadata stored in
        self.ts_ids.

        """
        column_query_parameter = build_column_query_parameter(self.columns)

        # For fetching the user specified timeseries id metadata, only the 'processed' ID data should be requested
        processing_query_parameter = build_processing_query_parameter(level="processed")

        self._get_ts_id_metadata(
            self.site_query_parameter
            + self.periodicity_query_parameter
            + column_query_parameter
            + processing_query_parameter
            + self.view_query_parameter
        )

    def _get_processing_timeseries_ids(self) -> None:
        """Collect the timeseries id metadata for any processing dependencies.

        In a similar way to `_get_user_timeseries_ids()` the metadata api service is queried and the extracted results
        are added to `self.ts_ids`. However, in this instance, the raw processing timeseries id metadata is requested
        for the current site(s) instead. Currently this is a hard coded list of variables: "BATTV",
        "SCANS"and "TNR01C", using a periodicity of PT30M.

        """
        # TODO: Determine these by looking at processing config dependencies in metadata
        column_query_parameter = build_column_query_parameter(PROCESSING_COLUMNS)

        processing_query_parameter = build_processing_query_parameter(level="raw")

        # TODO: Once this information is available from the metadata service, remove the hardcoding of the periodicity
        #   query parameter.

        # Hardcode the periodicity to PT30M to ensure the correct raw data is fetched for the processing dependencies
        periodicity_query_parameter = self._construct_periodicity_query_parameter("PT30M")

        self._get_ts_id_metadata(
            self.site_query_parameter
            + periodicity_query_parameter
            + column_query_parameter
            + processing_query_parameter
            + self.view_query_parameter
        )

    def _get_dependent_timeseries_ids(self) -> None:
        """
        Recurisvely identify any time series dependencies and fetch the corresponding metadata, adding the new
        time series id metadata entries into the main self.ts_ids dictionary.

        """
        dependent_timeseries_ids = self._identify_dependent_ts_ids()

        # Fetch the corresponding timeseries metadata for the list of dependent time series IDs identified previously.
        timeseries_id_parameter = build_timeseries_id_query_parameter(dependent_timeseries_ids)

        # TODO remove the limit parameter once FW-692 has been implemented
        self._get_ts_id_metadata(
            self.site_query_parameter + timeseries_id_parameter + self.view_query_parameter + [("_limit", 50)]
        )

    def _add_derivation_metadata(self) -> None:
        """
        For each time series id metadata object fetch and the corresponding the derivation metadata, storing it within
        the main timeseries id metadata.

        """
        # Get the derivation metadata for the timeseries IDs to be built
        ts_def_metadata = {
            ts_id["ts_def"]: handle_derivation_response(ts_id["ts_def"]) for ts_id in self.ts_ids.values()
        }

        # Add TS definition metadata to each timeseries ID
        self.ts_ids = merge_ts_def_metadata(self.ts_ids, ts_def_metadata)

    def _identify_dependent_ts_ids(self) -> List[str]:
        """Build a list of the dependencies for any existing ts_ids."""
        dependent_timeseries_ids = []
        for ts_id in self.ts_ids.keys():
            ts_name = re.match(URI_ID_EXTRACT_REGEX, ts_id).group(1)
            dependent_timeseries_list = load_dependent_datasets(ts_name)
            dependent_timeseries_ids.extend([dependent_ts.ts_id for dependent_ts in dependent_timeseries_list])

        return dependent_timeseries_ids

    def _load_raw_data(self) -> None:
        """Load the raw data for each time series."""
        for ts_id, ts_metadata in self.ts_ids.items():
            if ts_metadata["load"]:
                logger.info(f"Loading data for {ts_id}")
                ts = load_data(ts_metadata, self.start_date, self.end_date)
                if not ts.df.is_empty():
                    ts = add_initial_core_flags(ts)

                    # Add the data into the ts_ids dict
                    self.ts_ids[ts_id]["data"] = ts

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

    def _construct_site_query_parameter(self, sites: List[str]) -> List[Tuple[str, str]]:
        """Construct the site query parameter.

        Queries the metadata api for the list of available sites, and extracts then into a single list of strings
        before using this to validate the user provided list of sites required for processing. For example checking
        that all user requested sites are available etc.)

        The site query parameter is a list of tuples providing the IDs of all sites to be queried by the metadata api
        service, and the corresponding source key within the metadata to search by. For example:

            [
                ('originatingSite', 'http://fdri.ceh.ac.uk/id/site/cosmos-alic1'),
                ('originatingSite', 'http://fdri.ceh.ac.uk/id/site/cosmos-bunny')
            ]

        Args:
            sites: List of site IDs to build the site query for

        Returns:
            The site query parameter comprising of a list of tuples, each containing a single (key, value) pair.

        """
        metadata_sites = load_sites()
        metadata_sites = extract_site_ids(metadata_sites, network=self.network)

        sites = parser.validate_sites(sites, metadata_sites)
        site_query_parameter = build_site_query_parameter(sites=sites, network=self.network)

        return site_query_parameter

    @staticmethod
    def _construct_periodicity_query_parameter(periodicity: str) -> List[Tuple[str, str]]:
        """Construct the periodicity query parameter.

        The periodicity query parameter is a list of tuples providing the periodicity IDs to be queried by the metadata
        api service and the correspoinding source key within the metadata to search by. For example:

            [
                ('type.measure.aggregation.periodicity', 'PT30M')
            ]

        Args:
            periodicity: Code representing the periodicity to validate and construct the periodicity query parameter for

        Returns:
            The periodicity query parameter comprising of a list of tuples, each containing a single (key, value) pair.

        """
        periodicities = parser.validate_periodicity(periodicity)
        periodicity_query_parameter = build_periodicity_query_parameter(periodicities)

        return periodicity_query_parameter

    @staticmethod
    def _write_timeseries(ts_ids: Dict[str, Dict[str, str]], bucket_name: str, writer: S3Writer) -> None:
        """Write the timeseries data to S3.

        Args:
            ts: The timeseries object to write.
            bucket_name: The name of the S3 bucket.
            dataset: The name of the dataset.
            writer: The S3 writer object.

        """
        # Extracting some sample data to test write works to the new bucket
        # Use the hard coded processing column as always included for the time being
        # Proper write functionality to be implemented in FPM-494
        # TODO update ts_ids type once FPM-474 merged
        ts_id = ts_ids["http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-tnr01c_30min_raw"]
        dataframes = group_by_date(ts_id["data"].df)
        writer.write(
            bucket_name=bucket_name,
            dataset=ts_id["sourceDataset"],
            site_id=ts_id["sourceSite"],
            data=dataframes,
        )
