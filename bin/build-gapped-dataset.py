from databuilder.builders import ParquetBuilder
from databuilder.utils import initialse_directory
from pathlib import Path
from datetime import time
import os

# Building the paths

HERE = Path(__file__).parent
DATA_DIR = HERE.parent / "parquet-data"
COSMOS_DIR = DATA_DIR / "cosmos"
COSMOS_GAP_DIR = DATA_DIR / "cosmos-with-gaps"

# Creating the directory and copying files

initialse_directory(COSMOS_GAP_DIR / "PRECIP_1MIN_2024_LOOPED", COSMOS_DIR / "PRECIP_1MIN_2024_LOOPED", purge=True)

# Removing data

COSMOS_GAP_PRECIP_DIR = COSMOS_GAP_DIR / "PRECIP_1MIN_2024_LOOPED"

# Rows and cells removed
builder = ParquetBuilder(COSMOS_GAP_PRECIP_DIR / "2024-01" / "2024-01-17.parquet")
builder.build_all(row_removal_percent=30, cell_removal_percent=5)
builder.write_output()

# Emulating high level of cell corruption
builder.reset()
builder.target = COSMOS_GAP_PRECIP_DIR / "2024-01" / "2024-01-18.parquet"
builder.build_all(cell_removal_percent=90)
builder.write_output()

# No data before 17:00
builder.reset()
builder.target = COSMOS_GAP_PRECIP_DIR / "2024-01" / "2024-01-19.parquet"
builder.build_all(clear_after_time=time(hour=17))
builder.write_output()

# Making gap that crosses midnight from 23:00 - 01:00
# Also a gap that crosses midnight into a new month 22:00 - 04:23
builder.reset()
builder.target = COSMOS_GAP_PRECIP_DIR / "2024-01" / "2024-01-30.parquet"
builder.build_all(clear_after_time=time(hour=23))
builder.write_output()

builder.reset()
builder.target = COSMOS_GAP_PRECIP_DIR / "2024-01" / "2024-01-31.parquet"
builder.build_all(clear_before_time=time(hour=1), clear_after_time=time(hour=22))
builder.write_output()

builder.reset()
builder.target = COSMOS_GAP_PRECIP_DIR / "2024-02" / "2024-02-01.parquet"
builder.build_all(clear_before_time=time(hour=4, minute=23))
builder.write_output()

# Removing a full day
os.remove(COSMOS_GAP_PRECIP_DIR / "2024-02" / "2024-02-02.parquet")

builder.reset()
builder.target = COSMOS_GAP_PRECIP_DIR / "2024-02" / "2024-02-03.parquet"
builder.build_all(row_removal_percent=40, cell_removal_percent=60)
builder.write_output()

# Making very little and gappy data
builder.reset()
builder.target = COSMOS_GAP_PRECIP_DIR / "2024-02" / "2024-02-04.parquet"
builder.build_all(row_removal_percent=70, cell_removal_percent=60)
builder.write_output()