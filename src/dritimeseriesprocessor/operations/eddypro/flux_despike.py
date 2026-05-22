import numpy as np
import polars as pl


def spike_code(var: pl.Series, rg: pl.Series, z: float, days: int) -> pl.Series:
    """Detect and remove spikes using a sliding-window MAD approach.

    Operates separately for daytime (Rg >= 20) and nighttime (Rg < 20).
    Spike locations are set to null.

    Args:
        var: Time series to despike.
        rg: Solar radiation used as day/night discriminator.
        z: Spike sensitivity (scaled MADs). Default 5.5 is a good starting point.
        days: Moving window width in days.

    Returns:
        Copy of var with spike values set to null.
    """
    arr = var.to_numpy(allow_copy=True).astype(float)
    rg_arr = rg.to_numpy(allow_copy=True).astype(float)

    interval = days * 48
    n = len(arr)

    ind = np.arange(n)
    plus = ind + 1
    minus = ind - 1
    plus[-1] = n - 1
    minus[0] = 0
    minus[-1] = n - 1

    d = (arr - arr[minus]) - (arr[plus] - arr)
    dday = d.copy()
    dday[rg_arr < 20] = np.nan
    dnight = d.copy()
    dnight[rg_arr >= 20] = np.nan

    n_windows = int(np.floor(n / interval))
    for i in range(1, n_windows + 1):
        sl = slice((i - 1) * interval, i * interval)
        dday_w = dday[sl]
        dnight_w = dnight[sl]

        md_day = np.nanmedian(dday_w)
        md_night = np.nanmedian(dnight_w)
        mad_day = np.nanmedian(np.abs(dday_w - md_day))
        mad_night = np.nanmedian(np.abs(dnight_w - md_night))

        eq1_day = md_day - z * mad_day / 0.6745
        eq2_day = md_day + z * mad_day / 0.6745
        eq1_night = md_night - z * mad_night / 0.6745
        eq2_night = md_night + z * mad_night / 0.6745

        spikes = (
            (dday_w < eq1_day)
            | (dday_w > eq2_day)
            | (dnight_w < eq1_night)
            | (dnight_w > eq2_night)
        )
        arr[(i - 1) * interval + np.where(spikes)[0]] = np.nan

    return pl.Series(var.name, arr)


def despike_df(
    current_df: pl.DataFrame,
    history_df: pl.DataFrame,
    columns: list[str],
    reference_column: str,
    lookback_days: int = 13,
    sensitivity: float = 5.5,
    iterations: int = 10,
) -> pl.DataFrame:
    """Apply MAD despiking to the EddyPro bundle, adding despiked columns alongside originals.

    Concatenates history and current window before running spike_code so the algorithm
    has enough context. Returns only the current window rows with new columns added:
      - H_despiked: H with spikes set to null (first column in `columns`)
      - Tau_L2: Tau with spikes set to null (subsequent columns in `columns`)
      - H_L2: H_despiked with range check [-200, 600] W m-2 applied

    Args:
        current_df: EddyPro output for the current processing window.
        history_df: Prior processed data for lookback context.
        columns: Column names to despike, e.g. ["H", "Tau"].
        reference_column: Day/night discriminator column, e.g. "R_SW_in_Avg".
        lookback_days: Moving window width in days.
        sensitivity: Spike sensitivity (scaled MADs).
        iterations: Number of despiking passes.

    Returns:
        current_df with despiked columns added.
    """
    select_cols = ["time"] + columns + [reference_column]
    combined = pl.concat([history_df.select(select_cols), current_df.select(select_cols)]).sort("time")
    n_history = len(history_df)

    rg = combined[reference_column]
    despiked_cols = {}

    for col in columns:
        col_data = combined[col]
        for _ in range(iterations):
            col_data = spike_code(col_data, rg, z=sensitivity, days=lookback_days)
        despiked_cols[col] = col_data.slice(n_history)

    new_columns = []
    for i, col in enumerate(columns):
        if i == 0:
            new_columns.append(despiked_cols[col].alias(f"{col}_despiked"))
        else:
            new_columns.append(despiked_cols[col].alias(f"{col}_L2"))

    result = current_df.with_columns(new_columns)

    if "H" in columns:
        h_despiked_arr = despiked_cols["H"].to_numpy(allow_copy=True)
        h_l2 = pl.Series("H_L2", np.where((h_despiked_arr < -200) | (h_despiked_arr > 600), np.nan, h_despiked_arr))
        result = result.with_columns(h_l2)

    return result
