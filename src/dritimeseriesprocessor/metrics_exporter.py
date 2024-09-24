"""Module for exporting prometheus metrics."""

import logging
from dritimeseriesprocessor.logger import setup_logging
from prometheus_client import Counter, Gauge, Histogram, start_http_server

setup_logging()
logger = logging.getLogger(__name__)

class Metrics:
    def __init__(self):
        # Histograms
        self.preprocessing_time = Histogram('preprocessing_time_seconds', 'Time spent on preprocessing')
        self.qc_time = Histogram('qc_time_seconds', 'Time spent on quality control')
        self.s3_write_time = Histogram('s3_write_time_seconds', 'Time spent writing to S3')

        # Gauge for flags
        self.flags_added = Gauge('flags_added', 'Number of flags added to data')

        # Counters for successful/failed runs
        self.successful_runs = Counter('successful_runs_total', 'Number of successful runs')
        self.failed_runs = Counter('failed_runs_total', 'Number of failed runs')

    def setup_metrics(self) -> None:
        """Export metrics to port 8080."""
        try:
            start_http_server(8080)
            logger.info("Metrics server started on port 8080")
        except Exception as e:
            logger.error(f"Failed to start metrics server: {str(e)}")

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
metrics = Metrics()