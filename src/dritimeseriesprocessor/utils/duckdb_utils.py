"""Helpers related to duckdb"""

import duckdb


def get_duck_db_settings(conn: duckdb.DuckDBPyConnection) -> dict:
    """Return all active DuckDB settings for the given connection.

    Args:
        conn: An active DuckDB connection.

    Returns:
        A dictionary mapping setting names to their current values.
    """
    settings = conn.execute("SELECT name, value FROM duckdb_settings()").fetchall()
    return {name: value for name, value in settings}


def get_duck_db_extensions(conn: duckdb.DuckDBPyConnection) -> dict:
    """Return all active DuckDB extensions for the given connection.

    Args:
        conn: An active DuckDB connection.

    Returns:
        A dictionary mapping extensions names to whether they are installed and loaded.
    """
    extensions = conn.execute("SELECT extension_name, installed, loaded FROM duckdb_extensions()").fetchall()
    return {name: {"installed": inst, "loaded": loaded} for name, inst, loaded in extensions}


def get_duck_db_secrets(conn: duckdb.DuckDBPyConnection) -> dict:
    """Return all active DuckDB secrets for the given connection.

    Args:
        conn: An active DuckDB connection.

    Returns:
        A dictionary mapping secret names to their properties.
    """
    secrets = conn.execute("SELECT name, secret_string FROM duckdb_secrets()").fetchall()
    return {name: parse_secret_string(secret_string) for name, secret_string in secrets}


def parse_secret_string(secret_string: str) -> dict[str, str]:
    """Parse the given DuckDB secret string into its components.

    Args:
        secret_string: The string to parse.

    Returns:
        A dictionary mapping secret component names to their values.
    """
    items = {}

    for part in secret_string.split(";"):
        secret_part = part.strip()
        if not secret_part:
            continue

        # Split on the first '=' only (some values may contain '=')
        if "=" in secret_part:
            key, value = secret_part.split("=", 1)
            items[key.strip()] = value.strip()

    return items
