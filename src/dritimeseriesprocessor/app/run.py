"""
Entry point for a processor run: picks the run mode for the user's arguments and runs it.

What each mode does is in `run_modes.py`.
"""

from dritimeseriesprocessor.app.run_modes import HistoricRun, ListSitesRun, RunMode, StandardRun
from dritimeseriesprocessor.cli.selection import HistoricRunConfig, ListSitesRunConfig, RunConfig, StandardRunConfig
from dritimeseriesprocessor.configuration.app_config import AppConfig, app_config
from dritimeseriesprocessor.utils.timer import log_duration


@log_duration("Total time taken: ")
def run_from_config(run_config: RunConfig) -> None:
    """Run the processor in the mode, and with the selection and dates, given by the user's arguments.

    Args:
        run_config: The run configuration for the chosen mode.
    """
    cfg = app_config()
    runner = create_run_mode(run_config, cfg)
    runner.run()


def create_run_mode(run_config: RunConfig, cfg: AppConfig) -> RunMode:
    """Create the run mode that matches the type of run configuration.

    Args:
        run_config: The run configuration for the chosen mode.
        cfg: Application configuration.

    Returns:
        The run mode, ready to run.
    """
    match run_config:
        case StandardRunConfig():
            return StandardRun(cfg, run_config.selection, run_config.start_date, run_config.end_date)

        case HistoricRunConfig():
            return HistoricRun(cfg, run_config.selection)

        case ListSitesRunConfig():
            return ListSitesRun(cfg, run_config.selection, run_config.start_date, run_config.end_date)
