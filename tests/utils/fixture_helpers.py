from pathlib import Path

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def discover_json_test_cases(directory: str | Path) -> list[str]:
    """Discover all JSON files in a directory for use with @pytest.mark.parametrize.

    Returns:
        A list of file paths as strings.
    """
    directory = FIXTURES_DIR / Path(directory)
    return [str(p) for p in directory.glob("*.json")]
