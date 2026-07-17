import warnings

warnings.filterwarnings("ignore")

# Filter warnings form the logs
from importlib.metadata import PackageNotFoundError, version  # noqa: E402
from pathlib import Path  # noqa: E402

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent

try:
    __version__ = version("dri-timeseries-processor")
except PackageNotFoundError:
    __version__ = "unknown"
