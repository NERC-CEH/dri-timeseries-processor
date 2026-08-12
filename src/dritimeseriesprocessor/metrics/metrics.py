"""
Prometheus metrics utilities for the time-series processing pipeline.
"""

import logging

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, push_to_gateway

logger = logging.getLogger(__name__)


class Metrics:
    """Manages Prometheus metrics for a single processing run."""

    def __init__(self, pushgateway_url: str, job_name: str, site: str):
        """Initialise metrics object.

        Args:
            pushgateway_url: The hostname and port of the Pushgateway to send metrics to.
            job_name: Job identifier used by the Pushgateway to group run metrics.
            site: The site(s) processed by this run (a single site ID for the deployed Argo per-site fan-out,
                or a comma-separated list for ad-hoc multi-site runs).
        """
        self.registry = CollectorRegistry()

        self.time_load = Histogram("time_load_seconds", "Time spent loading data", registry=self.registry)
        self.time_write = Histogram("time_write_seconds", "Time spent writing", registry=self.registry)
        self.time_pipeline = Histogram("time_pipeline_seconds", "Time spent for full pipeline", registry=self.registry)

        self.success = Counter(
            "runs_successful_total", "Successful dataset processing runs", ["dataset"], registry=self.registry
        )
        self.failed = Counter(
            "runs_failed_total", "Failed dataset processing runs", ["dataset"], registry=self.registry
        )
        self.no_data = Counter(
            "runs_no_data_total", "Runs where no data was returned", ["dataset"], registry=self.registry
        )
        self.run_result = Gauge(
            "run_result", "1 if every dataset in the run succeeded, 0 if any dataset failed", registry=self.registry
        )

        self.pushgateway_url = pushgateway_url
        self.job_name = job_name
        self.site = site

    def export_metrics_to_pushgateway(self) -> None:
        """Export metrics to the prometheus pushgateway, grouped by site.

        The grouping key attaches a `site` label to every metric pushed here (dataset-level counters get
        both `site` and `dataset`), and stops concurrent per-site pods that share a job from overwriting
        each other's pushed metrics.
        """
        try:
            push_to_gateway(
                gateway=self.pushgateway_url,
                job=self.job_name,
                registry=self.registry,
                grouping_key={"site": self.site},
            )
        except Exception:
            logger.exception("Failed to export metrics to pushgateway")
