"""
Prometheus metrics utilities for the time-series processing pipeline.
"""

import logging

from prometheus_client import CollectorRegistry, Counter, Histogram, push_to_gateway

logger = logging.getLogger(__name__)


class Metrics:
    """Manages Prometheus metrics for a single processing run."""

    def __init__(self, pushgateway_url: str, job_name: str):
        """Initialise metrics object.

        Args:
            pushgateway_url: The hostname and port of the Pushgateway to send metrics to.
            job_name: Job identifier used by the Pushgateway to group run metrics.
        """
        self.registry = CollectorRegistry()

        self.time_corrections = Histogram(
            "time_corrections_seconds", "Time spent applying corrections", registry=self.registry
        )
        self.time_load = Histogram("time_load_seconds", "Time spent loading data", registry=self.registry)
        self.time_qc = Histogram("time_qc_seconds", "Time spent in quality control", registry=self.registry)
        self.time_infill = Histogram("time_infill_seconds", "Time spent infilling data", registry=self.registry)
        self.time_aggregate = Histogram("time_aggregate_seconds", "Time spent aggregating data", registry=self.registry)
        self.time_derive = Histogram("time_derive_seconds", "Time spent deriving data", registry=self.registry)
        self.time_write = Histogram("time_write_seconds", "Time spent writing", registry=self.registry)

        self.success = Counter("runs_successful_total", "Successful pipeline runs", registry=self.registry)
        self.failed = Counter("runs_failed_total", "Failed pipeline runs", registry=self.registry)
        self.no_data = Counter("runs_no_data_total", "Runs where no data was returned", registry=self.registry)

        self.pushgateway_url = pushgateway_url
        self.job_name = job_name

    def export_metrics_to_pushgateway(self) -> None:
        """Export metrics to the prometheus pushgateway."""
        try:
            push_to_gateway(gateway=self.pushgateway_url, job=self.job_name, registry=self.registry)
        except Exception:
            logger.exception("Failed to export metrics to pushgateway")
