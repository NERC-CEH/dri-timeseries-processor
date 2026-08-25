from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import polars as pl
import time_stream as ts
from time_stream.operation import Operation
from time_stream.utils import get_date_filter

from dritimeseriesprocessor import PACKAGE_ROOT
from dritimeseriesprocessor.models.domain_models.processing_config import DataProcessingMethodConfig
from dritimeseriesprocessor.utils.enums import ConfigurationType


def _observation_interval(config: DataProcessingMethodConfig) -> tuple[datetime, datetime | None] | None:
    if config.start_date is None:
        return None
    return config.start_date, config.end_date


class QcMethod(Operation, ABC):
    operation_type = ConfigurationType.QUALITY_CONTROL

    @abstractmethod
    def run(self, *args, **kwargs) -> pl.Series:
        pass


@QcMethod.register
class Range(QcMethod):
    name = "range"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "range",
            max_value=config.params["gt"],
            min_value=config.params["lt"],
            within=False,
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class BatteryVoltage(QcMethod):
    name = "battery_v"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "comparison",
            operator="<",
            compare_to=config.params["lt"],
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class Samples(QcMethod):
    name = "samples"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "comparison",
            operator="<",
            compare_to=config.params["lt"],
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class ErrorCode(QcMethod):
    name = "error_code"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "comparison",
            operator="is_in",
            compare_to=config.params["value"],
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class Spike(QcMethod):
    name = "spike"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "spike",
            threshold=config.params["gt"],
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class Nr01Temp(QcMethod):
    name = "nr01_temp"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "range",
            max_value=config.params["gt"],
            min_value=config.params["lt"],
            within=False,
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class HeatFluxPlateRemoval(QcMethod):
    name = "hfp_removal"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "time_range",
            max_value=datetime.strptime(config.params["time_le"], "%H:%M:%S").time(),
            min_value=datetime.strptime(config.params["time_ge"], "%H:%M:%S").time(),
            within=True,
            closed="both",
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class PluvioDiagnostic(QcMethod):
    name = "pluvio_diag"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "comparison",
            operator=">",
            compare_to=config.params["gt"],
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class SnowDaySignal(QcMethod):
    name = "snowd_signal"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "comparison",
            operator="<",
            compare_to=config.params["lt"],
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class TdtTSoil(QcMethod):
    name = "tdt_tsoil"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        return tf.qc_check(
            "comparison",
            operator="<",
            compare_to=config.params["lt"],
            column_name=tf.metadata["column_name"],
            observation_interval=_observation_interval(config),
        )


@QcMethod.register
class FluxQcFlag(QcMethod):
    """Apply EddyPro's internal quality flag to a flux variable.

    Receives the qc-flag container's TimeFrame via dep_ts, so tf.df[col]
    is e.g. qc_H. Flag value 2 (poor quality) is always rejected.
    """

    name = "flux_qc_flag"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        col = tf.metadata["column_name"]
        return tf.df[col] == 2


@QcMethod.register
class ManualRemoval(QcMethod):
    """Flag data points that appear in the manual flagging file.

    The file is a hand-maintained list of data points that have been checked by a person and found to be bad, for
    example during sensor maintenance or a known fault. Each row gives a site, one or more variables, and the date
    range that is affected.

    This is a temporary method until a proper manual flagging process has been implemented within the FDRI system.
    """

    name = "manual_removal"

    def run(self, tf: ts.TimeFrame, config: DataProcessingMethodConfig) -> pl.Series:
        # The network and site code are put into the params by QCPipeline, taken from the container.
        periods = self.flag_periods(config.params["network"], config.params["site_id"], tf.metadata["column_name"])

        flagged = pl.repeat(False, pl.len())
        for period in periods:
            flagged = flagged | get_date_filter(tf.time_name, period)

        return tf.df.select(flagged).to_series()

    @staticmethod
    @lru_cache
    def load_manual_flags(file_path: Path) -> dict[tuple[str, str], list[tuple[datetime, datetime | None]]]:
        """Read the manual flagging file and group the flagged periods by site and variable.

        Args:
            file_path: The manual flagging file to read.

        Returns:
            Flagged periods keyed by (site ID, variable name).
        """
        flags = pl.read_csv(file_path).with_columns(
            pl.col("SITE_ID").str.strip_chars().str.to_uppercase(),
            pl.col("START_DATETIME").str.to_datetime("%Y-%m-%d %H:%M:%S"),
            pl.col("END_DATETIME").str.to_datetime("%Y-%m-%d %H:%M:%S"),
            pl.col("VARIABLES_AFFECTED").str.split(";").alias("VARIABLE"),
        )
        flags = flags.explode("VARIABLE", empty_as_null=False).with_columns(
            pl.col("VARIABLE").str.strip_chars().str.to_uppercase()
        )

        # A trailing ";" leaves an empty variable name behind, which flags nothing.
        flags = flags.filter(pl.col("VARIABLE") != "")

        periods = defaultdict(list)
        for row in flags.iter_rows(named=True):
            periods[(row["SITE_ID"], row["VARIABLE"])].append((row["START_DATETIME"], row["END_DATETIME"]))

        return dict(periods)

    def flag_periods(self, network: str, site_id: str, column_name: str) -> list[tuple[datetime, datetime | None]]:
        """Get the periods that have been manually flagged for a site and variable.

        Includes any periods recorded against "ALL" for the site, which apply to every variable there.

        Args:
            network: Name of the network the site belongs to, e.g. "cosmos". Each network has its own file.
            site_id: Short site code, e.g. "ALIC1".
            column_name: Name of the data column, e.g. "TDT2_TSOIL".

        Returns:
            The flagged periods, or an empty list if nothing has been flagged for this site and variable.
        """
        manual_flags_file = PACKAGE_ROOT / "__assets__" / "manual_flagging" / network / "manual_flags.csv"
        periods = self.load_manual_flags(manual_flags_file)
        site_id = site_id.upper()
        return periods.get((site_id, column_name.upper()), []) + periods.get((site_id, "ALL"), [])
