import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import duckdb

from databuilder.enums import Operators


def set_random_cells_to_null(target: os.PathLike, percent: int, exclude: List[str]) -> None:
    """Sets random cells to NULL based of a percentage probability

    The randomness is set on each column separately. It does not clear full rows.

    Args:
        target: Path to the target parquet file.
        percent: The percentage of rows to change for each variable
        exclude: A list of columns to exclude.
    """

    temp_file = f"{target}.new"

    with duckdb.connect() as con:
        # Fetch column names for the table
        columns = con.execute(f"DESCRIBE SELECT * FROM READ_PARQUET('{target}');").fetchall()

        # # Construct the SQL query
        query = "SELECT "
        query += ", ".join(
            [
                f"CASE WHEN RANDOM() < 0.2 THEN NULL ELSE {col[0]} END AS {col[0]}" if col[0] not in exclude else col[0]
                for col in columns
            ]
        )
        query += f" FROM read_parquet('{target}')"

        modified_data = con.execute(query).fetchdf()

    modified_data.to_parquet(f"{target}.new")

    os.rename(temp_file, target)


def clear_percentage_of_rows(target: os.PathLike, percent: int) -> None:
    temp_file = f"{target}.new"

    with duckdb.connect() as con:
        query = f"SELECT * FROM READ_PARQUET('{target}') TABLESAMPLE reservoir({100 - percent}%);"

        modified_data = con.execute(query).fetchdf()

    modified_data.to_parquet(f"{target}.new")

    with duckdb.connect() as con:
        print(con.execute(f"SELECT * FROM READ_PARQUET('{target}');").fetchdf())
        print(con.execute(f"SELECT * FROM READ_PARQUET('{temp_file}');").fetchdf())


def clear_rows_by_time(target: os.PathLike, date_time: datetime, operator: Operators, time_fmt: str = "%H:%M") -> None:
    """Clears all rows relative to a given date or time.

    The time format is '%H:%M' by default and expects the Operators enum
    to specify the operation.

    Args:
        target: The target parquet file
        date_time: The datetime object specifying the clearing point
        operator: The comparison operation to apply (>, >=, <, <=, ==)
        time_fmt: The datetime format to clear with.
    """

    query = f"SELECT * FROM READ_PARQUET('{target}')"
    query += f" WHERE strftime('{time_fmt}', \"{datetime}\") {operator} {date_time.strftime(time_fmt)}"

    with duckdb.connect() as con:
        con.execute(query)


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


def main() -> None:
    table = Path(__file__).parent / "cosmos-with-gaps" / "PRECIP_1MIN_2024_LOOPED" / "2024-01" / "2024-01-30.parquet"
    excluded_columns = ["time", "SITE_ID", "RECORD"]
    set_random_cells_to_null(table, 0, excluded_columns)
    clear_percentage_of_rows(table, 90)


if __name__ == "__main__":
    main()
