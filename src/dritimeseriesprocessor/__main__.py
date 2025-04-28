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
timeseries_ids_to_process = load_datasets(
    site_query_parameter
    + periodicity_query_parameter
    + column_query_parameter
    + processing_query_parameter
    + view_query_parameter
)
timeseries_ids_to_process = extract_timeseries_id_metadata(timeseries_ids_to_process)


# Step 2
# Get derivation metadata for the timeseries IDs to be built
# Every timeseries ID will be dependent on another (raw or processed)
# Derivation metadata is held with the timeseries definition rather than the ID
# First extract all unique timeseries defs from the IDS to be processed
# Then extract all the dependencies associated with each timeseries definition and
# transform into required structure
unique_timeseries_defs = extract_unique_timeseries_defs(timeseries_ids_to_process)
timeseries_defs_for_processing = load_nested_timeseries_derivations(unique_timeseries_defs)


# Step 3
# Get timeseries ID metadata for all dependencies
# First extract all dependent timeseries definitions
# Then call the dataset endpoint with site and ts def to get the metadata
# Validate and transform response
dependent_timeseries_defs = extract_dependent_timeseries_defs(timeseries_defs_for_processing)
timeseries_def_parameter = build_timeseries_def_query_parameter(dependent_timeseries_defs)

# TODO remove the limit parameter once FW-692 has been implemented
dependent_timeseries_ids_to_process = load_datasets(
    site_query_parameter + timeseries_def_parameter + view_query_parameter + [("_limit", 50)]
)

dependent_timeseries_ids_to_process = extract_timeseries_id_metadata(dependent_timeseries_ids_to_process)


# Step 4
# Combine all the metadata into a single object for processing
# TODO (maybe) add method_type and inputs
timeseries_ids_to_process = timeseries_ids_to_process | dependent_timeseries_ids_to_process


# Start processing
# ----------------
# TODO Input data to be processed by dataset (to discuss)
# Get all the required data and merge into dataframes
# Process altogether and then separate back into timeseries required for each timeseries ID

# Currently just processing each raw input one by one
for ts_id, metadata in timeseries_ids_to_process.items():
    if metadata["processing_level"] == "raw":
        DATASET = metadata["sourceDataset"]
        COLUMNS = metadata["sourceColumnName"]
        BUCKET = metadata["sourceBucket"]
        SITES = metadata["sourceSite"]

        logger.info(
            f"Processing {DATASET} with columns {COLUMNS} for sites {SITES} between {start_date} and {end_date}"
        )

        try:
            # Setup s3
            # --------
            if app_config.environment == "local":
                s3_client = boto3.client("s3", endpoint_url=app_config.endpoint_url)
            else:
                s3_client = boto3.client("s3")

            # Ingress
            # -------
            data = data_manager.query_by_date_range(
                bucket_name=BUCKET,
                prefix=f"cosmos/dataset={DATASET}",
                start_date=start_date,
                end_date=end_date,
                site_ids=[SITES],
                columns=[COLUMNS],
            )

            if data.shape[0] == 0:
                metrics.record_no_data_run()
                logger.info("No data returned from the query.")

                # Push no data run metric
                metrics.export_metrics_to_pushgateway(
                    url=metrics.get_pushgateway_url(), job="timeseries-processor", registry=metrics.registry
                )

            else:
                logger.info(f"Retrieved data from s3: {data.shape}")

                # Dummy some data that will force some qc checks to run
                data = data.with_columns(
                    [
                        pl.Series([12 for i in range(len(data))]).alias("BATTV"),
                        pl.Series(i * 2 for i in range(len(data))).alias("PRECIP"),
                        pl.Series(i for i in range(len(data))).alias("SCANS"),
                    ]
                )

                # Add a missing value
                # data[-2, "TA"] = None

                logger.info(f"Added dummy data, shape: {data.shape}")

                # Initialise TimeSeries object
                # ---------------------------
                resolution = metadata["resolution"]
                periodicity = metadata["periodicity"]
                ts = TimeSeries(
                    data, "time", resolution, periodicity, supplementary_columns=["SITE_ID", "BATTV", "SCANS"]
                )

                # Initialise core flags
                ts = add_initial_core_flags(ts)

                # Preprocessing
                # ---------------
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
                ts = run_infilling(ts, ts_id, metadata)
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
                    dataset=DATASET,
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
