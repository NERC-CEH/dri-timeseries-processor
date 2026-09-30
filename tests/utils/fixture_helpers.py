import json
from pathlib import Path
from typing import Any

import pytest
from _pytest.mark.structures import ParameterSet

PARQUET_DATA_INPUT_DIR = Path(__file__).parent.parent.parent / "parquet-data" / "raw"
PARQUET_DATA_PROCESSED_DIR = Path(__file__).parent.parent.parent / "parquet-data" / "processed"
FLUX_DATA_DIR = Path(__file__).parent.parent.parent / "flux-data"
TEST_DATA_INPUT_DIR = Path(__file__).parent.parent / "data" / "inputs"
TEST_DATA_OUTPUT_DIR = Path(__file__).parent.parent / "data" / "outputs"
TEST_DATA_API_VALID = TEST_DATA_INPUT_DIR / "api_json" / "valid"
TEST_DATA_API_INVALID = TEST_DATA_INPUT_DIR / "api_json" / "invalid"
TEST_DATA_ASSETS_VALID = TEST_DATA_INPUT_DIR / "__assets__" / "valid"
TEST_DATA_ASSETS_INVALID = TEST_DATA_INPUT_DIR / "__assets__" / "invalid"
TEST_DATA_MOCK_METADATA = TEST_DATA_INPUT_DIR / "mock_metadata_api"
END_TO_END = Path(__file__).parent.parent / "end_to_end"


def discover_file_test_cases(directory: Path, glob_pattern: str = "*") -> list[ParameterSet]:
    """Discover all files in a directory for use with @pytest.mark.parametrize.

    Args:
          directory: Path to directory to discover files within
          glob_pattern: Optional pattern to filter files

    Returns:
        A list of pytest.param objects, each representing a file.
    """
    test_cases = []
    for path in directory.glob(glob_pattern):
        # Create a readable relative ID for test display
        relative_path_id = str(path.relative_to(TEST_DATA_INPUT_DIR))
        test_cases.append(pytest.param(str(path), id=relative_path_id))

    return test_cases


def discover_json_test_cases(directory: str | Path) -> list[ParameterSet]:
    """Discover all JSON files in a directory for use with @pytest.mark.parametrize."""
    directory = TEST_DATA_INPUT_DIR / Path(directory)
    return discover_file_test_cases(directory, glob_pattern="*.json")


def load_json_file(filepath: str | Path) -> dict[str, Any]:
    """Helper for loading input JSON files."""
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Fixture not found: {filepath}")

    with open(filepath, "r") as f:
        return json.load(f)


def load_json_string(json_str: str) -> dict[str, Any]:
    """Helper for loading JSON from a string."""
    return json.loads(json_str)


def load_declared_flag_columns() -> dict[tuple[str, str, str], list[str]]:
    """Read the flag columns each processed dataset declares in the recorded mock metadata.

    Returns:
        Flag column names, keyed by (site id, source column name, periodicity) - e.g.
        `("cosmos-chimn", "RN", "PT30M")`.
    """
    declared_flag_columns: dict[tuple[str, str, str], set[str]] = {}
    for path in TEST_DATA_MOCK_METADATA.glob("*.json"):
        response = load_json_file(path)
        for item in response.get("items", []):
            is_processed = item.get("processingLevel", {}).get("@id", "").endswith("/processed")
            if "sourceColumnName" not in item or not is_processed:
                continue

            flag_columns = {flag_column["columnName"] for flag_column in item.get("hasFlagColumn", [])}
            for site in item.get("originatingSite", []):
                site_id = site["@id"].rsplit("/", 1)[-1]
                for measure in item.get("measure", []):
                    key = (site_id, item["sourceColumnName"], measure["periodicity"])
                    declared_flag_columns.setdefault(key, set()).update(flag_columns)

    return {key: sorted(flag_columns) for key, flag_columns in declared_flag_columns.items()}


def discover_e2e_test_cases() -> list[ParameterSet]:
    """Discover all test cases from the test case JSON file for use with @pytest.mark.parametrize.

    Returns:
        A list of pytest.param objects, each representing a test case.
    """
    test_cases = []
    for test_case in load_json_file(END_TO_END / "test_cases.json")["test_cases"]:
        test_cases.append(
            pytest.param(
                test_case["network"],
                test_case["sites"],
                test_case["measured_variables"],
                test_case["derived_variables"],
                test_case["aggregated_variables"],
                test_case["periodicities"],
                test_case["start_date"],
                test_case["end_date"],
                test_case.get("check_variables"),
                id=test_case["id"],
            )
        )
    return test_cases
