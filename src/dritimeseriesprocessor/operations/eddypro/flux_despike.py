import numpy as np
import polars as pl

DAY_NIGHT_RADIATION_THRESHOLD = 20.0  # W m-2; radiation >= threshold is treated as daytime
MAD_TO_STD_SCALE = 0.6745  # scales the median absolute deviation to a standard-deviation estimate
HALF_HOURS_PER_DAY = 48  # number of 30-minute records in a day
H_RANGE_MIN = -200.0  # W m-2; lower bound for the H_L2 range check
H_RANGE_MAX = 600.0  # W m-2; upper bound for the H_L2 range check


def spike_code(series: pl.Series, radiation: pl.Series, sensitivity: float, window_days: int) -> pl.Series:
    """Detect and null spikes using a sliding-window MAD approach.

    Operates separately for daytime (radiation >= 20) and nighttime (radiation < 20).
    Flagged values are set to null.

    Args:
        series: Time series to despike.
        radiation: Solar radiation used as the day/night discriminator.
        sensitivity: Spike threshold in scaled MADs (5.5 is a good default).
        window_days: Width of each non-overlapping moving window, in days.
    """
    values = series.to_numpy(allow_copy=True).astype(float)
    radiation_values = radiation.to_numpy(allow_copy=True).astype(float)

    window_size = window_days * HALF_HOURS_PER_DAY
    n = len(values)

    indices = np.arange(n)
    next_index = indices + 1
    prev_index = indices - 1
    next_index[-1] = n - 1
    prev_index[0] = 0
    prev_index[-1] = n - 1

    # Double-difference highlights points that deviate from both neighbours.
    double_diff = (values - values[prev_index]) - (values[next_index] - values)
    daytime_diff = double_diff.copy()
    daytime_diff[radiation_values < DAY_NIGHT_RADIATION_THRESHOLD] = np.nan
    nighttime_diff = double_diff.copy()
    nighttime_diff[radiation_values >= DAY_NIGHT_RADIATION_THRESHOLD] = np.nan

    n_windows = int(np.floor(n / window_size))
    for i in range(1, n_windows + 1):
        window = slice((i - 1) * window_size, i * window_size)
        day_window = daytime_diff[window]
        night_window = nighttime_diff[window]

        day_median = np.nanmedian(day_window)
        night_median = np.nanmedian(night_window)
        day_mad = np.nanmedian(np.abs(day_window - day_median))
        night_mad = np.nanmedian(np.abs(night_window - night_median))

        day_lower = day_median - sensitivity * day_mad / MAD_TO_STD_SCALE
        day_upper = day_median + sensitivity * day_mad / MAD_TO_STD_SCALE
        night_lower = night_median - sensitivity * night_mad / MAD_TO_STD_SCALE
        night_upper = night_median + sensitivity * night_mad / MAD_TO_STD_SCALE

        spikes = (
            (day_window < day_lower)
            | (day_window > day_upper)
            | (night_window < night_lower)
            | (night_window > night_upper)
        )
        values[(i - 1) * window_size + np.where(spikes)[0]] = np.nan

    return pl.Series(series.name, values)


def despike_df(
    current_df: pl.DataFrame,
    history_df: pl.DataFrame,
    columns: list[str],
    reference_column: str,
    window_days: int = 13,
    sensitivity: float = 5.5,
    iterations: int = 1,
    output_names: dict[str, str] | None = None,
) -> pl.DataFrame:
    """Apply MAD despiking to the EddyPro bundle, adding despiked columns alongside originals.

    Prepends history to the current window so the algorithm has enough context, then returns
    only the current window's rows with new columns added per `output_names`, plus H_L2 if
    "H" is in `columns` (range-checked H after despiking, [-200, 600] W m-2).

    Args:
        current_df: EddyPro output for the current processing window.
        history_df: Prior processed data for window context.
        columns: Column names to despike, e.g. ["H", "Tau"].
        reference_column: Day/night discriminator column, e.g. "R_SW_in_Avg".
        window_days: Width of each non-overlapping MAD window, in days.
        sensitivity: Spike threshold in scaled MADs.
        iterations: Number of despiking passes.
        output_names: Mapping from input column name to output column name.
            Defaults to ``{col: f"{col}_L2" for col in columns}``.
    """
    if output_names is None:
        output_names = {col: f"{col}_L2" for col in columns}
    select_cols = ["time"] + columns + [reference_column]
    combined = pl.concat([history_df.select(select_cols), current_df.select(select_cols)]).sort("time")

    # spike_code tiles non-overlapping windows from the first row, so rows beyond the
    # last whole window are never evaluated. Drop the oldest rows so the windows align
    # to the end of the frame, ensuring the current window (always the most recent rows)
    # falls inside an evaluated window.
    window_size = window_days * HALF_HOURS_PER_DAY
    n_combined = len(combined)
    trim = n_combined % window_size if n_combined >= window_size else 0
    aligned = combined.slice(trim)

    radiation = aligned[reference_column]
    n_current = len(current_df)

    despiked = {}
    for col in columns:
        series = aligned[col]
        for _ in range(iterations):
            series = spike_code(series, radiation, sensitivity, window_days)
        despiked[col] = series.tail(n_current)

    new_columns = [despiked[col].alias(output_names[col]) for col in columns]
    result = current_df.with_columns(new_columns)

    if "H" in columns:
        h_values = despiked["H"].to_numpy(allow_copy=True)
        h_l2 = pl.Series("H_L2", np.where((h_values < H_RANGE_MIN) | (h_values > H_RANGE_MAX), np.nan, h_values))
        result = result.with_columns(h_l2)

    return result
