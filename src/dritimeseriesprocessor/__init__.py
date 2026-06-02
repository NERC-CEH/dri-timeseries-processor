from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent

try:
    __version__ = version("dri-timeseries-processor")
except PackageNotFoundError:
    __version__ = "unknown"
