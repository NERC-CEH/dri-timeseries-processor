import logging
import os
from datetime import date

import boto3
import polars as pl

from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.flagging.flagger import initialise_core_flags, update_quality_control_core_flags
from dritimeseriesprocessor.infilling.infiller import run_infilling
from dritimeseriesprocessor.logger import setup_logging
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.preprocessing.preprocessor import run_preprocess
from dritimeseriesprocessor.quality_control.quality_controller import run_quality_control
from dritimeseriesprocessor.s3_crud import data_manager
from dritimeseriesprocessor.s3_crud.write import S3Writer
from dritimeseriesprocessor.utils import group_by_date_site_id
from time_series import TimeSeries
from time_series.period import Period

metrics.setup_metrics()
setup_logging()

logger = logging.getLogger(__name__)

# Session parameters
DATASET='PRECIP_1MIN_2024_LOOPED'
START_DATE=date(2024, 3, 28)
END_DATE=date(2024, 3, 29)
# Optional
SITE_IDS="BUNNY"
# Optional
COLUMNS=["time", "SITE_ID", "P_BUCKET_RT", "P_LOADCELL_TEMP"]

try:
    # Setup s3
    # --------
    if "environment" not in os.environ:
        s3_client = boto3.client("s3", endpoint_url=app_config.endpoint_url)
    else:
        s3_client = boto3.client("s3")


    # Ingress
    # -------
    data = data_manager.query_by_date_range(
        app_config.level_0_bucket,
        prefix=f"cosmos/dataset={DATASET}",
        start_date=START_DATE,
        end_date=END_DATE,
        site_ids=SITE_IDS,
        columns=COLUMNS,
    )

    data = data.rename({"P_LOADCELL_TEMP": "TA"})

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
    data[2, "TA"] = None

    logger.info(f"Added dummy data, shape: {data.shape}")


    # Initialise TimeSeries object
    # ---------------------------
    resolution = Period.of_minutes(1)
    periodicity = Period.of_minutes(1)
    ts = TimeSeries(data, "time", resolution, periodicity, supplementary_columns=["SITE_ID", "BATTV", "SCANS"])

    # Initialise core flags
    ts = initialise_core_flags(ts)


    # Preprocessing
    # -------------
    ts.df = run_preprocess(ts.df)

    logger.info(f"Ran preprocessor successfully, shape: {ts.df.shape}")


    # Quality control
    # ---------------
    ts = run_quality_control(ts, remove=True)
    ts = update_quality_control_core_flags(ts)

    qcd_data = ts.df

    # Calculate the number of flags added
    qcflag_columns = [col for col in qcd_data.columns if col.endswith("_QCFLAG")]
    flags_count = len(qcflag_columns)

    logger.info(f"Number of QC flag columns: {flags_count}")
    metrics.increment_flags(flags_count)

    # show first 100 rows to show how qc flags have been applied
    with pl.Config(tbl_rows=100):
        logger.info(qcd_data.limit(100))


    # Infilling
    # ---------
    infld_data = run_infilling(qcd_data)

    # show first 100 rows to show how infill flags have been applied
    with pl.Config(tbl_rows=100):
        logger.info(infld_data.limit(100))


    # Writing
    # -------
    writer = S3Writer(s3_client)

    # Group data by date and site
    # If query parameters are stored as variables at the top of module,
    # could check date and site_id to see if we even need to do any grouping.
    dataframes = group_by_date_site_id(infld_data)

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
