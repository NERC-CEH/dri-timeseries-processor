import autosemver

try:
    __version__ = autosemver.packaging.get_current_version(project_name="dritimeseriesprocessor")
except RuntimeError:
    __version__ = "unknown version"
