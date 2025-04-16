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
from dritimeseriesprocessor.utils import extract_unique_timeseries_defs, group_by_date_site_id
from metadata_manager import api_manager
from metadata_manager.models.common import (
    build_column_query_parameter,
    build_periodicity_query_parameter,
    build_site_query_parameter,
)
from metadata_manager.models.service import load_datasets, load_nested_timeseries_derivations
from metadata_manager.transformers import extract_site_ids, extract_timeseries_id_metadata

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
# User arguments are combined to create the timeseries IDs to be processed.
# The metadata store is queried to see if they exist, and extract the required
# metadata for processing if so.
args = parser.parse_args(sys.argv[1:])

# Sites
# TODO build service and pydantic model for sites endpoint FW-694
metadata_sites = extract_site_ids(asyncio.run(metadata.fetch_sites()), network="cosmos")
sites = parser.validate_sites(args.sites, metadata_sites)
site_query_parameter = build_site_query_parameter(sites)

# Periodicity
periodicities = parser.validate_periodicity(args.periodicity)
periodicity_query_parameter = build_periodicity_query_parameter(periodicities)

# Columns
columns = parser.validate_columns(args.columns)
column_query_parameter = build_column_query_parameter(columns)

# Processing level
processing_query_parameter = [("type.processingLevel", "http://fdri.ceh.ac.uk/ref/common/processing-level/processed")]

# View
view_query_parameter = [("_view", "timeseries")]

# Dates
start_date, end_date = parser.build_date_range(args.period, args.end_date, app_config.environment)


# Get metadata for timeseries IDs to be processed
# -----------------------------------------------
# Validate and load API response before transforming to required format
timeseries_ids_to_process = load_datasets(
    site_query_parameter
    + periodicity_query_parameter
    + column_query_parameter
    + processing_query_parameter
    + view_query_parameter
)
timeseries_ids_to_process = extract_timeseries_id_metadata(timeseries_ids_to_process)


# Get derivation metadata for datasets to be processed
# ----------------------------------------------------
# Derivation metadata is held with the timeseries definition rather than the ID
# So first extract all unique timeseries defs from the IDS to be processed
unique_timeseries_defs = extract_unique_timeseries_defs(timeseries_ids_to_process)


# Extract all the dependencies associated with each timeseries definition and
# transform into required format
timeseries_defs_for_processing = load_nested_timeseries_derivations(unique_timeseries_defs)


# TODO Combine timeseries ID and defs dicts; add processing level. (to discuss)

# TODO Undertake processing (to discuss)
# Hardcoded a sample combined ts_id and ts_def dictionary that can be processed
# to make the processor at least run through.
timeseries_ids_to_process = [
    {
        "output": {
            "resolution": "PT30M",
            "periodicity": "PT30M",
            "sourceBucket": "ukceh-fdri-staging-timeseries-qc",
            "sourceDataset": "PROCESSED_DATA_30MIN",
            "sourceColumnName": "TA",
            "sourceSite": "cosmos-alic1",
        },
        "ts_id": "http://fdri.ceh.ac.uk/id/dataset/cosmos-alic1-ta_30min_processed",
        "ts_def": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_processed",
    },
    {
        "output": {
            "resolution": "PT30M",
            "periodicity": "PT30M",
            "sourceBucket": "ukceh-fdri-staging-timeseries-qc",
            "sourceDataset": "PROCESSED_DATA_30MIN",
            "sourceColumnName": "TA",
            "sourceSite": "cosmos-bunny",
        },
        "ts_id": "http://fdri.ceh.ac.uk/id/dataset/cosmos-bunny-ta_30min_processed",
        "ts_def": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_processed",
    },
]

for item in timeseries_ids_to_process:
    site = item["output"]["sourceSite"].rsplit("-")[-1]

    item["inputs"] = [{}]
    item["inputs"][0]["ts_id"] = f"http://fdri.ceh.ac.uk/id/dataset/cosmos-{site}-ta_30min_raw"
    item["inputs"][0]["ts_def"] = "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ta_30min_raw"
    item["inputs"][0]["periodicity"] = 30  # This comes as PT30M so would need formatting
    item["inputs"][0]["resolution"] = 30  # This comes as PT30M so would need formatting
    item["inputs"][0]["sourceBucket"] = "ukceh-fdri-staging-timeseries-level-0"
    item["inputs"][0]["sourceDataset"] = "LIVE_SOILMET_30MIN"
    item["inputs"][0]["sourceColumnName"] = "TA"
    item["inputs"][0]["sourceSite"] = site.upper()

    item["output"]["derivation_type"] = "http://fdri.ceh.ac.uk/ref/common/configuration-type/calculate"
    item["output"]["derivation_method"] = "http://fdri.ceh.ac.uk/ref/common/method/calculate-calculate-ta"


# Start processing
# ----------------
# TODO Input data to be processed by dataset (to discuss)
# Get all the required data and merge into dataframes
# Process altogether and then separate back into timeseries required for each timeseries ID

logger.info(
    f"Building timeseries IDs {[ts_id['ts_id'] for ts_id in timeseries_ids_to_process]}"
    f" between {start_date} and {end_date}"
)

# Currently just processing each input one by one
for metadata in timeseries_ids_to_process:
    for item in metadata["inputs"]:
        DATASET = item["sourceDataset"]
        COLUMNS = item["sourceColumnName"]
        BUCKET = item["sourceBucket"]
        SITES = item["sourceSite"]

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
                data[-2, "TA"] = None

                logger.info(f"Added dummy data, shape: {data.shape}")

                # Initialise TimeSeries object
                # ---------------------------
                resolution = Period.of_minutes(item["resolution"])
                periodicity = Period.of_minutes(item["periodicity"])
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
                # TODO How do we write out when processing variables rather than whole dataset?
                writer = S3Writer(s3_client)

                # TODO (edits) Group data by date and site
                # Currently only need to group by date but this will all change anyway
                # Data to be split for individual timeseries ID after being grouped.
                dataframes = group_by_date_site_id(ts.df)

                writer.write(
                    bucket_name=metadata["output"]["sourceBucket"],
                    dataset=metadata["output"]["sourceDataset"],
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
