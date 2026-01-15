import os

from dritimeseriesprocessor.utils.enums import Environment


def detect_environment() -> Environment:
    """Determines the runtime environment the process is running in."""
    env_value = os.environ.get("environment", "local")

    try:
        return Environment(env_value)
    except ValueError:
        raise ValueError(f"Unsupported environment '{env_value}'. Expected one of: {[e.value for e in Environment]}")
