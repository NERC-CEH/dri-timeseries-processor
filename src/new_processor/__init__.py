from pathlib import Path

import autosemver

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent

try:
    __version__ = autosemver.packaging.get_current_version(project_name="time-series-processor")
except Exception:
    __version__ = "0.0.0"
