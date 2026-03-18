from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, call

from dritimeseriesprocessor.io_backend.flux_io import FluxS3Client


class TestFluxS3Client:
    def test_download_raw_dat_files_downloads_files_across_date_range(self, tmp_path: Path) -> None:
        storage = MagicMock()
        storage.list_keys_with_prefix.side_effect = [
            ["fdri/dataset=Flux/site=PLYNL/date=2026-01-20/file_a.dat"],
            [],
            ["fdri/dataset=Flux/site=PLYNL/date=2026-01-22/file_b.dat"],
        ]

        def fake_download_file(bucket: str, key: str, local_path: Path) -> None:
            local_path.write_text(f"{bucket}:{key}")

        storage.download_file.side_effect = fake_download_file
        client = FluxS3Client(storage_client=storage)

        downloaded = client.download_raw_dat_files(
            bucket="raw-bucket",
            site="PLYNL",
            dataset="Flux",
            network="fdri",
            start_date=date(2026, 1, 20),
            end_date=date(2026, 1, 22),
            local_dir=tmp_path / "raw",
        )

        assert [path.name for path in downloaded] == ["file_a.dat", "file_b.dat"]
        assert storage.list_keys_with_prefix.call_args_list == [
            call("raw-bucket", "fdri/dataset=Flux/site=PLYNL/date=2026-01-20/"),
            call("raw-bucket", "fdri/dataset=Flux/site=PLYNL/date=2026-01-21/"),
            call("raw-bucket", "fdri/dataset=Flux/site=PLYNL/date=2026-01-22/"),
        ]
        assert storage.download_file.call_args_list == [
            call("raw-bucket", "fdri/dataset=Flux/site=PLYNL/date=2026-01-20/file_a.dat", downloaded[0]),
            call("raw-bucket", "fdri/dataset=Flux/site=PLYNL/date=2026-01-22/file_b.dat", downloaded[1]),
        ]

    def test_upload_output_files_uploads_recursive_output_tree(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        top_level_file = output_dir / "summary.csv"
        nested_file = output_dir / "subdir" / "details.txt"
        nested_file.parent.mkdir(parents=True)
        top_level_file.write_text("summary")
        nested_file.write_text("details")

        storage = MagicMock()
        client = FluxS3Client(storage_client=storage)

        client.upload_output_files(
            bucket="processed-bucket",
            output_dir=output_dir,
            network="fdri",
            site="PLYNL",
            processed_dataset="eddypro-full-output",
            start_date=date(2026, 1, 20),
        )

        uploaded = sorted(
            (args[1], args[2]) for args, _ in [call_item for call_item in storage.upload_file.call_args_list]
        )
        expected = sorted(
            [
                (
                    "fdri/dataset=eddypro-full-output/site=PLYNL/date=2026-01-20/subdir/details.txt",
                    nested_file,
                ),
                (
                    "fdri/dataset=eddypro-full-output/site=PLYNL/date=2026-01-20/summary.csv",
                    top_level_file,
                ),
            ]
        )
        assert uploaded == expected
