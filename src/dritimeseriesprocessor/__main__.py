import logging
import os
from datetime import date

import boto3
import polars as pl

from dritimeseriesprocessor.configuration import app_config
from dritimeseriesprocessor.flagging import initialise_core_flags
from dritimeseriesprocessor.infilling.infiller import run_infilling
from dritimeseriesprocessor.logger import setup_logging
from dritimeseriesprocessor.metrics_exporter import metrics
from dritimeseriesprocessor.preprocessing.preprocessor import run_preprocess
from dritimeseriesprocessor.quality_control.quality_controller import run_quality_control
from dritimeseriesprocessor.s3_crud import data_manager
from dritimeseriesprocessor.s3_crud.write import S3Writer
from time_series import TimeSeries
from time_series.period import Period

metrics.setup_metrics()
setup_logging()

logger = logging.getLogger(__name__)

try:
    # Get S3 Client
    if "environment" not in os.environ:
        s3_client = boto3.client("s3", endpoint_url=app_config.endpoint_url)
    else:
        s3_client = boto3.client("s3")

    # Get data
    prefix = "cosmos/dataset=PRECIP_1MIN_2024_LOOPED"
    start_date = date(2024, 2, 3)
    end_date = date(2024, 2, 4)
    data = data_manager.query_by_date_range(
        app_config.level_0_bucket,
        prefix,
        start_date,
        end_date,
        site_ids="BUNNY",
        columns=["time", "SITE_ID", "P_BUCKET_RT", "P_LOADCELL_TEMP"],
    )

    data = data.rename({"P_LOADCELL_TEMP": "TA"})

    logger.info(f"Retrieved data from s3: {data.shape}")

    # Dummy some data that will force some qc checks to run
    data = data.with_columns(
        [
            pl.Series([0 if ((i // 20) % 2 == 0) else 100 for i in range(len(data))]).alias("BATTV"),
            pl.Series(i * 2 for i in range(len(data))).alias("PRECIP"),
            pl.Series(i for i in range(len(data))).alias("SCANS"),
        ]
    )

    logger.info(f"Added dummy data, shape: {data.shape}")

    # Initilise TimeSeries object.
    resolution = Period.of_minutes(1)
    periodicity = Period.of_minutes(1)
    ts = TimeSeries.from_polars(data, "time", resolution, periodicity, supp_col_names=["SITE_ID", "BATTV", "SCANS"])

    # Initialise core flags
    ts = initialise_core_flags(ts)

    data = ts.df
    data = data.with_columns(pl.col("time").dt.convert_time_zone("UTC").dt.replace_time_zone(None))

    # Preprocessing
    preprocessed_data = run_preprocess(data)

    logger.info(f"Ran preprocessor successfully, shape: {preprocessed_data.shape}")

    # Quality control
    qcd_data = run_quality_control(preprocessed_data)

    # Calculate the number of flags added
    qcflag_columns = [col for col in qcd_data.columns if col.endswith("_QCFLAG")]
    flags_count = len(qcflag_columns)

    logger.info(f"Number of QC flag columns: {flags_count}")
    metrics.increment_flags(flags_count)

    # show first 100 rows to show how qc flags have been applied
    with pl.Config(tbl_rows=100):
        logger.info(qcd_data.limit(100))

    # Infilling
    infld_data = run_infilling(qcd_data)

    # show first 100 rows to show how infill flags have been applied
    with pl.Config(tbl_rows=100):
        logger.info(infld_data.limit(100))

    # Writing output
    writer = S3Writer(s3_client)
    writer.write(
        bucket_name=app_config.qc_bucket,
        key=f"""cosmos/dataset=PRECIP_1MIN_2024_LOOPED/
            {writer._build_date_range_partition_key(start_date, end_date)}.parquet""",
        body=infld_data,
    )

    metrics.record_successful_run()
    logger.info("Processing completed successfully")

    # Push all metrics at the end of successful processing
    metrics.export_metrics_to_pushgateway(
        url="pushgateway.monitoring.svc:9091", job="timeseries-processor", registry=metrics.registry
    )

except Exception as e:
    metrics.record_failed_run()
    logger.exception(f"An error occurred during processing: {str(e)}")

    # Push all metrics even if an exception occurs
    metrics.export_metrics_to_pushgateway(
        url="pushgateway.monitoring.svc:9091", job="timeseries-processor", registry=metrics.registry
    )

    raise
