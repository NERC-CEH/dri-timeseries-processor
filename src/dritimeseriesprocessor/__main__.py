import logging
import sys

import boto3
from time_stream import TimeSeries

from dritimeseriesprocessor import parser
from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.flagging.flagger import add_initial_core_flags
from dritimeseriesprocessor.logger import setup_logging
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.processor import load_data, process_timeseries
from dritimeseriesprocessor.s3_crud.write import S3Writer
from dritimeseriesprocessor.utils import (
    extract_dependent_timeseries_defs,
    extract_unique_timeseries_defs,
    group_by_date_site_id,
)
from metadata_manager.models.common import (
    build_column_query_parameter,
    build_periodicity_query_parameter,
    build_site_query_parameter,
    build_timeseries_def_query_parameter,
)
from metadata_manager.models.service import load_datasets, load_nested_timeseries_derivations, load_sites
from metadata_manager.transformers import extract_site_ids, extract_timeseries_id_metadata

logger = logging.getLogger(__name__)
setup_logging()


# Setup metrics
# -------------
metrics.setup_metrics()

# Setup s3
# --------
if app_config.environment == "local":
    s3_client = boto3.client("s3", endpoint_url=app_config.endpoint_url)
else:
    s3_client = boto3.client("s3")


# Parse and validate arguments
# ----------------------------
# User arguments are combined to create the timeseries IDs to be processed.
# The metadata store is queried to see if they exist, and extract the required
# metadata for processing if so.
args = parser.parse_args(sys.argv[1:])

# Sites
metadata_sites = load_sites()
metadata_sites = extract_site_ids(metadata_sites, network="cosmos")
sites = parser.validate_sites(args.sites, metadata_sites)
site_query_parameter = build_site_query_parameter(sites)

# Periodicity
periodicities = parser.validate_periodicity(args.periodicity)
periodicity_query_parameter = build_periodicity_query_parameter(periodicities)

# Columns
columns = parser.validate_columns(args.columns)
column_query_parameter = build_column_query_parameter(columns)

# Processing level
# TODO extract to build_processing_query_parameter
processing_query_parameter = [("type.processingLevel", "http://fdri.ceh.ac.uk/ref/common/processing-level/processed")]

# View
# TODO extract to build_view_query_parameter
view_query_parameter = [("_view", "timeseries")]

# Dates
start_date, end_date = parser.build_date_range(args.period, args.end_date, app_config.environment)


# Get metadata for timeseries IDs to be processed
# -----------------------------------------------

# Step 1:
# Extract timeseries IDs to build from user arguments
# Validate and load API response metadata for each timeseries ID
# Transform response into required structure
user_timeseries_ids_response = load_datasets(
    site_query_parameter
    + periodicity_query_parameter
    + column_query_parameter
    + processing_query_parameter
    + view_query_parameter
)
user_timeseries_ids_metadata = extract_timeseries_id_metadata(user_timeseries_ids_response)


# Step 2
# Get derivation metadata for the timeseries IDs to be built
# Every timeseries ID will be dependent on another (raw or processed)
# Derivation metadata is held with the timeseries definition rather than the ID
# First extract all unique timeseries defs from the IDS to be processed
# Then extract all the dependencies associated with each timeseries definition and
# transform into required structure
unique_timeseries_defs = extract_unique_timeseries_defs(user_timeseries_ids_metadata)
timeseries_defs_derivation_map = load_nested_timeseries_derivations(unique_timeseries_defs)


# Step 3
# Get timeseries ID metadata for all dependencies
# First extract all dependent timeseries definitions
# Then call the dataset endpoint with site and ts def to get the metadata
# Validate and transform response
dependent_timeseries_defs = extract_dependent_timeseries_defs(timeseries_defs_derivation_map)
timeseries_def_parameter = build_timeseries_def_query_parameter(dependent_timeseries_defs)

# TODO remove the limit parameter once FW-692 has been implemented
dependent_timeseries_ids_response = load_datasets(
    site_query_parameter + timeseries_def_parameter + view_query_parameter + [("_limit", 50)]
)
dependent_timeseries_ids_metadata = extract_timeseries_id_metadata(dependent_timeseries_ids_response)


# Step 4
# Combine all the metadata into a single object for processing
# TODO (maybe) add method_type and inputs
ts_ids = user_timeseries_ids_metadata | dependent_timeseries_ids_metadata


# Load raw data
# -------------
for ts_id, ts_metadata in ts_ids.items():
    if ts_metadata["processing_level"] != "raw":
        continue

    # Can only load data for timeseries ids with no derivation method.
    if timeseries_defs_derivation_map[ts_metadata["ts_def"]].get("method_type") is not None:
        continue

    logger.info(f"Loading data for {ts_id}")
    ts = load_data(ts_metadata, start_date, end_date)
    if ts is not None:
        ts = add_initial_core_flags(ts)

        # Add the data into the ts_ids dict
        ts_ids[ts_id]["data"] = ts
    else:
        logger.warning(f"No data found for {ts_id}")


# Process data
# ------------
try:
    ts_ids = process_timeseries(ts_ids)
except Exception as e:
    metrics.record_failed_run()
    logger.exception(f"An error occurred during processing: {str(e)}")
    metrics.export_metrics_to_pushgateway(
        url=metrics.get_pushgateway_url(), job="timeseries-processor", registry=metrics.registry
    )
    raise

# TODO Agregations and derivations here


# Writing
# -------
# TODO We need to establish dataset names for the processed timeseries's
# after they are processed. Therefore for now, removing the writing of data
# writer = S3Writer(s3_client)


# TODO How do we write out when processing variables rather than whole dataset?
def write_timeseries(ts: TimeSeries, bucket_name: str, dataset: str, writer: S3Writer) -> None:
    """Write the timeseries data to S3.

    Args:
        ts: The timeseries object to write.
        bucket_name: The name of the S3 bucket.
        dataset: The name of the dataset.
        writer: The S3 writer object.

    """
    # TODO (edits) Group data by date and site
    # Currently only need to group by date but this will all change anyway
    # Data to be split for individual timeseries ID after being grouped.
    dataframes = group_by_date_site_id(ts.df)

    writer.write(
        bucket_name=bucket_name,
        dataset=dataset,
        data=dataframes,
    )


metrics.record_successful_run()
logger.info("Processing completed successfully")

# Push all metrics at the end of successful processing
metrics.export_metrics_to_pushgateway(
    url=metrics.get_pushgateway_url(), job="timeseries-processor", registry=metrics.registry
)
