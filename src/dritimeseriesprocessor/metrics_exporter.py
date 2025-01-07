"""Module for exporting prometheus metrics."""

import logging
import os

from prometheus_client import CollectorRegistry, Counter, Histogram, push_to_gateway

from dritimeseriesprocessor.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


class Metrics:
    def __init__(self) -> None:
        """Initialize the Metrics"""

        # Histograms
        self.preprocessing_time = Histogram("preprocessing_time", "Time spent on preprocessing")
        self.qc_time = Histogram("qc_time", "Time spent on quality control")
        self.s3_write_time = Histogram("s3_write_time", "Time spent writing to S3")

        # Counter for flags
        self.flags_added = Counter("flags_added_total", "Total number of flags added to data")

        # Counters for successful/failed runs
        self.successful_runs = Counter("successful_runs_total", "Number of successful runs")
        self.failed_runs = Counter("failed_runs_total", "Number of failed runs", ["reason"])

    def setup_metrics(self) -> None:
        """Setup metrics."""
        self.registry = CollectorRegistry()
        self.registry.register(self.preprocessing_time)
        self.registry.register(self.qc_time)
        self.registry.register(self.s3_write_time)
        self.registry.register(self.flags_added)
        self.registry.register(self.successful_runs)
        self.registry.register(self.failed_runs)

    def get_pushgateway_url(self) -> str:
        """Gets the Pushgateway URL based on environment settings.

        Returns:
            str: The Pushgateway URL, either for local or k8s environment.
        """
        pushgateway_url = "pushgateway.monitoring.svc:9091"
        if "environment" not in os.environ:
            pushgateway_url = "localhost:9091"
        return pushgateway_url

    def export_metrics_to_pushgateway(self, url: str, job: str, registry: CollectorRegistry) -> None:
        """Export metrics to the prometheus pushgateway.

        Args:
            url: URL for pushgateway
            job: The job name
            registry: An instance of the collector registry
        """
        push_to_gateway(gateway=url, job=job, registry=registry)

    def track_preprocessing_time(self) -> float:
        return self.preprocessing_time.time()

    def track_qc_time(self) -> float:
        return self.qc_time.time()

    def track_s3_write_time(self) -> float:
        return self.s3_write_time.time()

    def increment_flags(self, count: int) -> None:
        self.flags_added.inc(count)

    def record_successful_run(self) -> None:
        self.successful_runs.inc()

    def record_failed_run(self, reason: str) -> None:
        self.failed_runs.labels(reason).inc()


metrics = Metrics()
