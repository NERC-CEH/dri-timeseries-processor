import asyncio
import logging
import sys

import boto3
import polars as pl
from time_stream import TimeSeries
from time_stream.period import Period

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
from dritimeseriesprocessor.utils import group_by_date_site_id, split_data_for_processing
from metadata_manager import api_manager
from metadata_manager.transformers import extract_site_ids, extract_dataset_metadata
from metadata_manager.models.service import load_datasets
from metadata_manager.models.common import build_site_query_parameter

logger = logging.getLogger(__name__)
setup_logging()


# Setup metrics
# -------------
metrics.setup_metrics()

# Setup connection to the metadata API
# ------------------------------------
metadata = api_manager.MetadataAPIManager(host=app_config.metadata_api_url, network="cosmos")


# Parse and validate arguments
# ----------------------------
# User arguments are combined to create the dataset(s) to be built.
# The metadata store is queried to see if they exist, and extract the required
# metadata for building if so.
args = parser.parse_args(sys.argv[1:])

# Sites
metadata_sites = extract_site_ids(asyncio.run(metadata.fetch_sites()), network="cosmos")
sites = parser.validate_sites(args.sites, metadata_sites)
site_query_parameter = build_site_query_parameter(sites)

# TODO: Periodicity FW-548
# Hardcoded
periodicity_query_parameter = [("type.measure.aggregation.periodicity", "PT30M")]

# TODO: Variables FW-549
# Hardcoded
variable_query_paremeter = [("type.measure.variable", "http://fdri.ceh.ac.uk/ref/common/cop/temp_air")]

# TODO Processing level (ticket not yet created)
# Hardcoded
processing_query_parameter = [("type.processingLevel", "http://fdri.ceh.ac.uk/ref/common/processing-level/processed")]

# View parameter
view_query_parameter = [("_view", "timeseries")]


# Extract metadata for the desired dataset
datasets_to_build = load_datasets(site_query_parameter + periodicity_query_parameter +
                                variable_query_paremeter + processing_query_parameter + view_query_parameter)

processing_metadata = extract_dataset_metadata(datasets_to_build, "output")


# TODO: Get dependencies
# Each dataset to build is dependent on other timeseries.
# Potential method:
# For each entry in processing_parameters, add the dependency metadata to
# an 'input' key using extract_datatset_metadata.

# Hard coding dependent datasets
for item in processing_metadata:
    site = item['output']['sourceSite'].rsplit("-")[-1]

    item['input'] = {}
    item['input']['ts_id'] = f"http://fdri.ceh.ac.uk/id/dataset/cosmos-{site}-ta_30min_raw"
    item['input']['ts_def'] = "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_raw"
    item['input']['periodicity'] = 30 # This comes as PT30M so would need formatting
    item['input']['resolution'] = 30
    item['input']['sourceBucket'] = "ukceh-fdri-staging-timeseries-level-0"
    item['input']['sourceDataset'] = "LIVE_SOILMET_30MIN"
    item['input']['sourceColumnName'] = "TA"
    item['input']['sourceSite'] = site.upper()

# TODO (Maybe) Undertake some grouping to optimise
# number of queries to duckDB

# Dates
start_date, end_date = parser.build_date_range(args.period, args.end_date, app_config.environment)
logger.info(f"Processing level 0 data between {start_date} and {end_date}, {sites}")


# Start processing
# ----------------

for metadata in processing_metadata:
    DATASET=metadata["input"]["sourceDataset"]
    VARIABLES=metadata["input"]["sourceColumnName"]
    BUCKET=metadata["input"]["sourceBucket"]
    SITES=metadata["input"]["sourceSite"]

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
            columns=[VARIABLES]
        )

        if data.shape[0] == 0:
            metrics.record_no_data_run()
            logger.info("No data returned from the query. Ending pipeline.")

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
            data[-2, "TA"] = None

            logger.info(f"Added dummy data, shape: {data.shape}")


            # Initialise TimeSeries object
            # ---------------------------
            resolution = Period.of_minutes(metadata["input"]["resolution"])
            periodicity = Period.of_minutes(metadata["input"]["periodicity"])
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
            ts = run_infilling(ts, site)
            ts = update_infill_core_flags(ts)

            # show first 100 rows to show how infill flags have been applied
            with pl.Config(tbl_rows=100):
                logger.info(ts.df.limit(100))

            # Writing
            # -------
            writer = S3Writer(s3_client)

            # Group data by date and site
            # Note: Might not need to group by site anymore. Depends on what
            # we do with grouping for optimising the query
            dataframes = group_by_date_site_id(ts.df)

            writer.write(
                bucket_name=metadata['output']['sourceBucket'],
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
