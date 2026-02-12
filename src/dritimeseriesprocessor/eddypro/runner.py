from __future__ import annotations

import json
import logging
import shutil
import subprocess
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any

from dritimeseriesprocessor.eddypro.template_fill import fill_tokens
from dritimeseriesprocessor.storage.storage_client import S3StorageClient

logger = logging.getLogger(__name__)


def run_eddypro(
    *,
    storage_client: S3StorageClient,
    network: str,
    site: str,
    start: datetime,
    end: datetime,
    site_cfg: dict[str, Any],
) -> int:
    """Run EddyPro for one site over a time window.

    This is a local runner:
    - pulls raw + ancillary from S3 (LocalStack in dev)
    - renders EddyPro config files from templates + site config
    - runs `eddypro_rp` and `eddypro_fcc`
    - uploads outputs + logs + a run manifest back to S3
    """
    _assert_eddypro_binaries_available()

    storage = site_cfg["storage"]

    source_bucket = str(storage["source_bucket"])
    source_dataset = str(storage["source_dataset"])
    destination_bucket = str(storage["destination_bucket"])
    destination_dataset = str(storage["destination_dataset"])

    raw_prefix = f"{network}/dataset={source_dataset}/site={site}/date={start:%Y-%m-%d}/"
    dynamic_metadata_prefix = f"{network}/ancillary/dynamic_metadata/site={site}/"
    biomet_prefix = f"{network}/ancillary/biomet/site={site}/"
    output_prefix = build_eddypro_output_prefix(network=network, dataset=destination_dataset, site=site, start=start)

    workdir = _build_workdir(site=site, start=start)
    if workdir.exists():
        shutil.rmtree(workdir, ignore_errors=True)

    (workdir / "input" / "raw").mkdir(parents=True, exist_ok=True)
    (workdir / "input" / "ancillary").mkdir(parents=True, exist_ok=True)
    (workdir / "generated").mkdir(parents=True, exist_ok=True)
    (workdir / "output" / site).mkdir(parents=True, exist_ok=True)
    (workdir / "logs").mkdir(parents=True, exist_ok=True)
    (workdir / "tmp").mkdir(parents=True, exist_ok=True)

    rc: int = 1
    run_error: BaseException | None = None
    try:
        raw_downloaded = download_s3_prefix_to_dir(storage_client, source_bucket, raw_prefix, workdir / "input" / "raw")
        logger.info("Downloaded %s raw files from s3://%s/%s", raw_downloaded, source_bucket, raw_prefix)

        dyn_key = select_ancillary_key(storage_client, source_bucket, dynamic_metadata_prefix, site)
        biom_key = select_ancillary_key(storage_client, source_bucket, biomet_prefix, site)

        download_s3_object_to_file(
            storage_client,
            source_bucket,
            dyn_key,
            workdir / "input" / "ancillary" / "dynamic_metadata.txt",
        )
        download_s3_object_to_file(
            storage_client,
            source_bucket,
            biom_key,
            workdir / "input" / "ancillary" / "biomet.csv",
        )

        processing_file = render_eddypro_configs(
            workdir=workdir,
            site_cfg=site_cfg,
            start=start,
            end=end,
        )

        rc = run_eddypro_engine(workdir=workdir, processing_file=processing_file, log_dir=workdir / "logs")
        return rc

    except BaseException as exc:
        run_error = exc
        raise

    finally:
        try:
            generated_uploaded = upload_dir_to_s3_prefix(
                storage_client,
                destination_bucket,
                f"{output_prefix}generated/",
                workdir / "generated",
            )
            logs_uploaded = upload_dir_to_s3_prefix(
                storage_client,
                destination_bucket,
                f"{output_prefix}logs/",
                workdir / "logs",
            )
            outputs_uploaded = upload_dir_to_s3_prefix(
                storage_client,
                destination_bucket,
                f"{output_prefix}output/{site}/",
                workdir / "output" / site,
            )
            logger.info(
                "Uploaded artifacts to s3://%s/%s (generated=%s logs=%s outputs=%s)",
                destination_bucket,
                output_prefix,
                generated_uploaded,
                logs_uploaded,
                outputs_uploaded,
            )
        except BaseException:
            logger.exception("Failed uploading run artifacts to s3://%s/%s", destination_bucket, output_prefix)
            if run_error is None:
                raise
        shutil.rmtree(workdir, ignore_errors=True)


def _read_template(name: str) -> str:
    """Read a bundled EddyPro template file as text."""
    return resources.files("dritimeseriesprocessor.eddypro.templates").joinpath(name).read_text(encoding="utf-8")


def render_eddypro_configs(*, workdir: Path, site_cfg: dict[str, Any], start: datetime, end: datetime) -> Path:
    """Render EddyPro processing + project config files into the run workdir."""
    config = site_cfg
    project = config["project"]
    site = config["site"]

    site_id = str(site["id"])
    processing_out = workdir / "generated" / "processing.eddypro"
    metadata_out = workdir / "generated" / "project.metadata"
    out_dir = workdir / "output" / site_id
    out_dir.mkdir(parents=True, exist_ok=True)

    processing_out.write_text(
        fill_tokens(
            _read_template("eddypro_processing.template.ini"),
            {
                "FILE_NAME": str(processing_out),
                "PROJECT_TITLE": str(project["title"]),
                "PROJECT_ID": str(project["id"]),
                "FILE_PROTOTYPE": str(project["file_prototype"]),
                "PROJ_FILE": str(metadata_out),
                "DYN_METADATA_FILE": str(workdir / "input" / "ancillary" / "dynamic_metadata.txt"),
                "PR_SUBSET": "1",
                "PR_START_DATE": start.strftime("%Y-%m-%d"),
                "PR_START_TIME": start.strftime("%H:%M"),
                "PR_END_DATE": end.strftime("%Y-%m-%d"),
                "PR_END_TIME": end.strftime("%H:%M"),
                "SA_START_DATE": start.strftime("%Y-%m-%d"),
                "SA_END_DATE": end.strftime("%Y-%m-%d"),
                "SA_START_TIME": start.strftime("%H:%M"),
                "SA_END_TIME": end.strftime("%H:%M"),
                "OUT_PATH": str(out_dir),
                "BIOM_FILE": str(workdir / "input" / "ancillary" / "biomet.csv"),
                "DATA_PATH": str(workdir / "input" / "raw"),
            },
        ),
        encoding="utf-8",
    )

    metadata_out.write_text(
        fill_tokens(
            _read_template("eddypro_metadata.template.ini"),
            {
                "PROJECT_TITLE": str(project["title"]),
                "PROJECT_ID": str(project["id"]),
                "PROJECT_START_DATE": start.strftime("%Y-%m-%d"),
                "PROJECT_END_DATE": end.strftime("%Y-%m-%d"),
                "METADATA_FILE_NAME": str(metadata_out),
                "DATA_PATH": str(workdir / "input" / "raw"),
                "SITE_NAME": str(site["name"]),
                "SITE_ID": site_id,
                "LATITUDE": str(site["latitude"]),
                "LONGITUDE": str(site["longitude"]),
                "ALTITUDE": str(site["altitude"]),
            },
        ),
        encoding="utf-8",
    )

    return processing_out


def run_eddypro_engine(*, workdir: Path, processing_file: Path, log_dir: Path) -> int:
    """Execute `eddypro_rp` then `eddypro_fcc` and return the final return code."""
    env = str(workdir)

    rp_log = (log_dir / "eddypro_rp.log").open("wb")
    rc = subprocess.run(
        [
            "eddypro_rp",
            "--system",
            "linux",
            "--mode",
            "desktop",
            "--caller",
            "console",
            "--environment",
            env,
            str(processing_file),
        ],
        cwd=str(workdir),
        stdout=rp_log,
        stderr=subprocess.STDOUT,
        check=False,
    ).returncode
    rp_log.close()
    if rc != 0:
        return rc

    fcc_log = (log_dir / "eddypro_fcc.log").open("wb")
    rc = subprocess.run(
        [
            "eddypro_fcc",
            "--system",
            "linux",
            "--mode",
            "desktop",
            "--caller",
            "console",
            "--environment",
            env,
            str(processing_file),
        ],
        cwd=str(workdir),
        stdout=fcc_log,
        stderr=subprocess.STDOUT,
        check=False,
    ).returncode
    fcc_log.close()
    return rc


def list_s3_keys_with_prefix(client: S3StorageClient, bucket: str, prefix: str) -> list[str]:
    """List all non-directory object keys under an S3 prefix (paginated)."""
    keys: list[str] = []
    continuation_token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if continuation_token is not None:
            kwargs["ContinuationToken"] = continuation_token
        response = client.client.list_objects_v2(**kwargs)
        keys.extend([obj["Key"] for obj in response.get("Contents", []) if not obj["Key"].endswith("/")])
        if not response.get("IsTruncated"):
            break
        continuation_token = response.get("NextContinuationToken")
        if continuation_token is None:
            break
    return keys


def select_ancillary_key(client: S3StorageClient, bucket: str, prefix: str, site: str) -> str:
    """Pick a deterministic ancillary object key, preferring ones containing the site id."""
    keys = sorted(list_s3_keys_with_prefix(client, bucket, prefix))
    if not keys:
        raise SystemExit(f"No objects found under s3://{bucket}/{prefix}")
    preferred = [key for key in keys if site in Path(key).name]
    return sorted(preferred or keys)[0]


def download_s3_prefix_to_dir(client: S3StorageClient, bucket: str, prefix: str, destination_dir: Path) -> int:
    """Download all objects under an S3 prefix into a local directory."""
    keys = list_s3_keys_with_prefix(client, bucket, prefix)
    if not keys:
        raise SystemExit(f"No objects found under s3://{bucket}/{prefix}")

    downloaded = 0
    for key in keys:
        relative = key.removeprefix(prefix).lstrip("/")
        if not relative:
            continue
        download_s3_object_to_file(client, bucket, key, destination_dir / relative)
        downloaded += 1
    return downloaded


def download_s3_object_to_file(client: S3StorageClient, bucket: str, key: str, destination_path: Path) -> None:
    """Download one S3 object to a local file path."""
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    response = client.client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    try:
        with destination_path.open("wb") as stream:
            for chunk in body.iter_chunks(chunk_size=1024 * 1024):
                if chunk:
                    stream.write(chunk)
    finally:
        body.close()


def upload_dir_to_s3_prefix(client: S3StorageClient, bucket: str, prefix: str, source_dir: Path) -> int:
    """Upload all files in a local directory to an S3 prefix."""
    if not source_dir.is_dir():
        return 0
    if not prefix.endswith("/"):
        raise ValueError(f"prefix must end with '/': {prefix}")

    uploaded = 0
    for path in source_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source_dir).as_posix()
        client.put_bytes(bucket, f"{prefix}{relative}", path.read_bytes())
        uploaded += 1
    return uploaded


def _assert_eddypro_binaries_available() -> None:
    """Fail fast if required EddyPro binaries are not on PATH."""
    missing = [name for name in ("eddypro_rp", "eddypro_fcc") if shutil.which(name) is None]
    if missing:
        raise SystemExit(f"Missing EddyPro binaries on PATH: {', '.join(missing)}")


def build_eddypro_output_prefix(*, network: str, dataset: str, site: str, start: datetime) -> str:
    """Build the processed-bucket output prefix for one EddyPro run."""
    return (
        f"{network}/dataset={dataset}/site={site}/date={start:%Y-%m-%d}/"
    )

def _build_workdir(*, site: str, start: datetime, root: Path = Path("/tmp/driflux/eddypro")) -> Path:
    """Build a unique local scratch directory for a site/window run."""
    window_start_id = start.strftime("%Y%m%d%H%M")
    return (root / f"site={site}" / f"window_start={window_start_id}").resolve()
