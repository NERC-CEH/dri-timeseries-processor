"""Module for methods that don't belong anywhere else"""

import os
import shutil
from pathlib import Path
from typing import Optional


def _create_directory(dst: os.PathLike, purge: bool = False) -> None:
    """Creates a directory with an option to clear the contents

    Args:
        dst: The directory path
        purge: Purges files if the directory already exists
    """

    if not isinstance(dst, Path):
        dst = Path(dst)

    if dst.exists() and purge:
        shutil.rmtree(dst)

    if not dst.exists():
        os.makedirs(dst)


def _copy_files(dst: os.PathLike, src: Optional[os.PathLike] = None) -> None:
    """Copies files from a directory

    Args:
        dst: The destination directory.
        src: The source directory, defaults to the data directory
    """

    if not isinstance(dst, Path):
        dst = Path(dst)

    if not src:
        src = Path(__file__).parents[2] / "parquet-data" / "cosmos"

    if not isinstance(src, Path):
        src = Path(src)

    shutil.copytree(src, dst, dirs_exist_ok=True)


def initialise_directory(dst: os.PathLike, src: Optional[os.PathLike] = None, purge: bool = False) -> None:
    """Initialises a directory and populates it with Parquet files

    Args:
        dst: The destination directory.
        src: The source directory, defaults to the data directory
        purge: Purges files if the directory already exists
    """

    _create_directory(dst, purge)
    _copy_files(dst, src)
