import isodate
from isodate import ISO8601Error


def validate_iso8601_duration(duration: str) -> bool:
    """
    Validate if the given string is a valid ISO 8601 duration.
    """
    try:
        isodate.parse_duration(duration)
        return True
    except ISO8601Error:
        return False
