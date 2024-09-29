"""Module for exporting prometheus metrics."""

import logging
import os
from dritimeseriesprocessor.logger import setup_logging
from prometheus_client import Counter, Histogram, CollectorRegistry, write_to_textfile

setup_logging()
logger = logging.getLogger(__name__)

class Metrics:
    def __init__(self, metrics_dir_path=None):
        """
        Initialize the Metrics class.

        :param metrics_dir_path: Optional. The directory path where metric files will be written.
                                 If not provided, defaults to a 'metrics' directory in the current working directory.
        """
        self.registry = CollectorRegistry()

        # Histograms
        self.preprocessing_time = Histogram('preprocessing_time_seconds', 'Time spent on preprocessing', registry=self.registry)
        self.qc_time = Histogram('qc_time_seconds', 'Time spent on quality control', registry=self.registry)
        self.s3_write_time = Histogram('s3_write_time_seconds', 'Time spent writing to S3', registry=self.registry)

        # Counter for flags
        self.flags_added = Counter('flags_added_total', 'Total number of flags added to data', registry=self.registry)

        # Counters for successful/failed runs
        self.successful_runs = Counter('successful_runs_total', 'Number of successful runs', registry=self.registry)
        self.failed_runs = Counter('failed_runs_total', 'Number of failed runs', registry=self.registry)

        self.set_metrics_dir_path(metrics_dir_path)

    def set_metrics_dir_path(self, metrics_dir_path=None):
        """
        Set or update the metrics directory path.

        :param metrics_dir_path: Optional. The directory path where metric files will be written.
                                 If not provided, defaults to a 'metrics' directory in the current working directory.
        """
        if metrics_dir_path is None:
            self.metrics_dir = os.path.join(os.getcwd(), 'metrics')
        else:
            self.metrics_dir = metrics_dir_path
        
        os.makedirs(self.metrics_dir, exist_ok=True)
        logger.info(f"Metrics directory set to: {self.metrics_dir}")

    def setup_metrics(self) -> None:
        """Initialize the metric files."""
        try:
            self.write_metrics()
            logger.info(f"Metric files initialized in {self.metrics_dir}")
        except Exception as e:
            logger.error(f"Failed to initialize metric files: {str(e)}")

    def write_metrics(self) -> None:
        """Write current metrics to individual files."""
        metrics = {
            'preprocessing_time': self.preprocessing_time,
            'qc_time': self.qc_time,
            's3_write_time': self.s3_write_time,
            'flags_added': self.flags_added,
            'successful_runs': self.successful_runs,
            'failed_runs': self.failed_runs
        }

        for name, metric in metrics.items():
            try:
                file_path = os.path.join(self.metrics_dir, f"{name}.txt")
                registry = CollectorRegistry()
                registry.register(metric)
                write_to_textfile(file_path, registry)
                logger.info(f"Metric {name} written to {file_path}")
            except Exception as e:
                logger.error(f"Failed to write metric {name} to file: {str(e)}")

    def track_preprocessing_time(self):
        return self.preprocessing_time.time()

    def track_qc_time(self):
        return self.qc_time.time()

    def track_s3_write_time(self):
        return self.s3_write_time.time()

    def increment_flags(self, count):
        self.flags_added.inc(count)

    def record_successful_run(self):
        self.successful_runs.inc()

    def record_failed_run(self):
        self.failed_runs.inc()

# Create an instance of the Metrics class
#metrics = Metrics()

# To use a custom metrics directory path, initialize as follows:
# metrics = Metrics(metrics_dir_path='/path/to/custom/metrics/directory')
metrics = Metrics(metrics_dir_path='/tmp/metrics')