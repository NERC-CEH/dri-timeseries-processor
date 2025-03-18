import asyncio
import logging
import sys

import boto3
import polars as pl

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
from metadata_manager.transformers import extract_site_ids
from time_series import TimeSeries
from time_series.period import Period

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
# All user inputs are checked against the metadata store as this is the source of truth
# Any input that isnt in the store is removed from the query
args = parser.parse_args(sys.argv[1:])

# Sites
metadata_sites = extract_site_ids(asyncio.run(metadata.fetch_sites()), network="cosmos")
sites = parser.validate_sites(args.sites, metadata_sites)

# TODO: Resolution FW-548
# TODO: Variables FW-549

# Dates
start_date, end_date = parser.build_date_range(args.period, args.end_date, app_config.environment)
logger.info(f"Processing level 0 data between {start_date} and {end_date}, {sites}")


# Session parameters
# ------------------
# These will be removed in FW-548 and FW-549
DATASET = "LIVE_SOILMET_30MIN"
# Optional
VARIABLES = ["time", "SITE_ID", "TA", "PA"]

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
        app_config.level_0_bucket,
        prefix=f"cosmos/dataset={DATASET}",
        start_date=start_date,
        end_date=end_date,
        site_ids=sites,
        columns=VARIABLES,
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

        # Split data by sites and add metadata
        # ------------------------------------
        # Hard coding periodicity and resolution metadata atm but should be able
        # to extract from the work in FW-548 and FW-549
        # This method likely to change when the metadata gets more complex i.e.
        # multiple resolutions with different variables.
        metadata = {"resolution": 30, "periodicity": 30}
        data = split_data_for_processing(data, metadata)

        for site, timeseries, metadata in data:
            logger.info(f"Processing site: {site}")

            # Initialise TimeSeries object
            # ---------------------------
            resolution = Period.of_minutes(metadata["resolution"])
            periodicity = Period.of_minutes(metadata["periodicity"])
            ts = TimeSeries(
                timeseries, "time", resolution, periodicity, supplementary_columns=["SITE_ID", "BATTV", "SCANS"]
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
