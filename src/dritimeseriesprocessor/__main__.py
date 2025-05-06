import logging
import sys

import boto3
import polars as pl
from time_stream import TimeSeries

from dritimeseriesprocessor import parser
from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.flagging.flagger import (
    add_initial_core_flags,
    update_infill_core_flags,
    update_preprocess_core_flags,
    update_quality_control_core_flags,
)
from dritimeseriesprocessor.infilling.infiller import run_infilling
from dritimeseriesprocessor.logger import setup_logging
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.preprocessing.preprocessor import run_preprocess
from dritimeseriesprocessor.quality_control.quality_controller import run_quality_control
from dritimeseriesprocessor.s3_crud import data_manager
from dritimeseriesprocessor.s3_crud.write import S3Writer
from dritimeseriesprocessor.utils import (
    extract_dependent_timeseries_defs,
    extract_unique_timeseries_defs,
    group_by_date_site_id,
    group_timeseries_to_process,
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
user_timeseries_ids_metadata = load_datasets(
    site_query_parameter
    + periodicity_query_parameter
    + column_query_parameter
    + processing_query_parameter
    + view_query_parameter
)
user_timeseries_ids_metadata = extract_timeseries_id_metadata(user_timeseries_ids_metadata)


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
dependent_timeseries_ids = load_datasets(
    site_query_parameter + timeseries_def_parameter + view_query_parameter + [("_limit", 50)]
)
dependent_timeseries_ids = extract_timeseries_id_metadata(dependent_timeseries_ids)


# Step 4
# Combine all the metadata into a single object for processing
# TODO (maybe) add method_type and inputs
all_timeseries_ids_metadata = user_timeseries_ids_metadata | dependent_timeseries_ids


# Step 5
# Group TS IDs into groups that can be processed together
# Currently this is by site, resolution and periodicity
# TODO - We want to be able to process differing resolutions/periodicities and sites together: FW-687
grouped_timeseries_to_process = group_timeseries_to_process(all_timeseries_ids_metadata, timeseries_defs_derivation_map)


# Setup s3
# --------
if app_config.environment == "local":
    s3_client = boto3.client("s3", endpoint_url=app_config.endpoint_url)
else:
    s3_client = boto3.client("s3")


# Process raw data
# ----------------
# We process each group of timeseries IDs together
for ts_group in grouped_timeseries_to_process.values():
    ts_ids = ts_group["timeseries_ids"]
    logger.info(f"Processing group {ts_group} with {len(ts_ids)} timeseries IDs")

    site_id = ts_group["site_id"]
    resolution = ts_group["resolution"]
    periodicity = ts_group["periodicity"]

    # Establish data to load
    # ----------------------
    data_to_load = {}
    for ts_id in ts_ids:
        # Get the timeseries IDs with no process method
        ts_metadata = all_timeseries_ids_metadata[ts_id]

        dataset = ts_metadata["sourceDataset"]
        bucket_name = ts_metadata["sourceBucket"]
        column_name = ts_metadata["sourceColumnName"]

        # Setup loading details by dataset and bucket name
        if dataset not in data_to_load:
            data_to_load[dataset] = {}

        if bucket_name not in data_to_load[dataset]:
            data_to_load[dataset][bucket_name] = {
                "columns": set(),
            }

        data_to_load[dataset][bucket_name]["columns"].add(column_name)

    # Load data
    # ---------
    data = None
    for dataset, buckets in data_to_load.items():
        # We join data from all datasets / buckets within this group together
        for bucket_name, params in buckets.items():
            logger.info(
                f"Processing {dataset} with columns {params['columns']} for site {site_id} "
                f"between {start_date} and {end_date}"
            )

            # Ingress
            # -------
            bucket_data = data_manager.query_by_date_range(
                bucket_name=bucket_name,
                prefix=f"cosmos/dataset={dataset}",
                start_date=start_date,
                end_date=end_date,
                site_ids=[site_id],
                columns=params["columns"],
            )

            if bucket_data.shape[0] == 0:
                metrics.record_no_data_run()
                logger.info("No data returned from the query.")

                # Push no data run metric
                metrics.export_metrics_to_pushgateway(
                    url=metrics.get_pushgateway_url(), job="timeseries-processor", registry=metrics.registry
                )

            else:
                logger.info(f"Retrieved data from s3: {bucket_data.shape}")

                # Dummy some data that will force some qc checks to run
                bucket_data = bucket_data.with_columns(
                    [
                        pl.Series([12 for i in range(len(bucket_data))]).alias("BATTV"),
                        pl.Series(i for i in range(len(bucket_data))).alias("SCANS"),
                    ]
                )
                logger.info(f"Added dummy data, shape: {bucket_data.shape}")

                if data is None:
                    data = bucket_data
                else:
                    # Join the new data to the existing data
                    matching_columns = set(data.columns) & set(bucket_data.columns)
                    # We expect matching columns to be time and site cols, and to be the same
                    # If there are matching data columns with differing data, we want this
                    # to fail
                    data = data.join(bucket_data, left_on=matching_columns, right_on=matching_columns, how="left")

    # Initialise TimeSeries object
    # ----------------------------
    ts = TimeSeries(data, "time", resolution, periodicity, supplementary_columns=["SITE_ID", "BATTV", "SCANS"])

    # Start processing
    # ----------------
    # Find a timeseries IDs that do not require processing, i.e. they are to be loaded
    # from the database

    try:
        # Initialise core flags
        ts = add_initial_core_flags(ts)

        # Preprocessing
        # -------------
        ts = run_preprocess(ts)
        ts = update_preprocess_core_flags(ts)

        logger.info(f"Ran preprocessor successfully, shape: {ts.df.shape}")

        # Quality control
        # ---------------
        ts = run_quality_control(ts, remove=True)
        ts = update_quality_control_core_flags(ts)

        # Calculate the number of flags added
        qcflag_columns = [col for col in ts.columns if col.endswith("_QCFLAG")]
        flags_count = len(qcflag_columns)

        logger.info(f"Number of QC flag columns: {flags_count}")
        metrics.increment_flags(flags_count)

        # show first 100 rows to show how qc flags have been applied
        with pl.Config(tbl_rows=100):
            logger.info(ts.df.limit(100))

        # Infilling
        # ---------
        ts = run_infilling(ts, ts_ids, all_timeseries_ids_metadata)
        ts = update_infill_core_flags(ts)

        # show first 100 rows to show how infill flags have been applied
        with pl.Config(tbl_rows=100):
            logger.info(ts.df.limit(100))

        # Writing
        # -------
        # TODO How do we write out when processing variables rather than whole dataset?
        writer = S3Writer(s3_client)

        # TODO (edits) Group data by date and site
        # Currently only need to group by date but this will all change anyway
        # Data to be split for individual timeseries ID after being grouped.
        dataframes = group_by_date_site_id(ts.df)

        writer.write(
            bucket_name=app_config.qc_bucket,
            dataset=dataset,
            data=dataframes,
        )

        metrics.record_successful_run()
        logger.info("Processing completed successfully")

        # Push all metrics at the end of successful processing
        metrics.export_metrics_to_pushgateway(
            url=metrics.get_pushgateway_url(), job="timeseries-processor", registry=metrics.registry
        )

    except Exception as e:
        metrics.record_failed_run()
        logger.exception(f"An error occurred during processing: {str(e)}")

        # Push all metrics even if an exception occurs
        metrics.export_metrics_to_pushgateway(
            url=metrics.get_pushgateway_url(), job="timeseries-processor", registry=metrics.registry
        )

        raise
