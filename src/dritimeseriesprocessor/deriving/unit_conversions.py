# TODO: update these to be Calculations?

def hpa_to_kpa(data):
    """Convert data from hectopascals (hPa) to kilopascals (kPa)

    Args:
        data: Data with hPa units to convert

    Returns:
        Data converted to kPa
    """
    return data * 0.1


def watts_to_megajoules(data, period):
    """Convert data from Watts (W) to Megajoules (MJ) per time period

    1 Watt = 1 Joule per second
    1 Megajoule = 1,000,000 Joules
    Therefore conversion is number of seconds in period, divided by 1,000,000

    Args:
        data: Data with W units to convert
        period: Time period

    Returns:
        Data converted to MJ
    """
    if period.timedelta is None:
        raise ValueError("Time period cannot be month-based.")
    period_seconds = period.timedelta.total_seconds()
    return data * (period_seconds / 1e6)
