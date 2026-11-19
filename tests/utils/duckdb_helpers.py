"""Helpers for checking how a DuckDB connection has been set up."""

import duckdb


def get_duck_db_setting(conn: duckdb.DuckDBPyConnection, name: str) -> object:
    """Return the current value of one DuckDB setting.

    Args:
        conn: An active DuckDB connection.
        name: The name of the setting.

    Returns:
        The setting's value
    """
    row = conn.execute("SELECT current_setting(?)", [name]).fetchone()
    return row[0] if row else None


def get_duck_db_extensions(conn: duckdb.DuckDBPyConnection) -> dict:
    """Return all DuckDB extensions for the given connection.

    Args:
        conn: An active DuckDB connection.

    Returns:
        A dictionary mapping extension names to whether they are installed and loaded.
    """
    extensions = conn.execute("SELECT extension_name, installed, loaded FROM duckdb_extensions()").fetchall()
    return {name: {"installed": installed, "loaded": loaded} for name, installed, loaded in extensions}


def get_duck_db_secrets(conn: duckdb.DuckDBPyConnection) -> dict:
    """Return all DuckDB secrets for the given connection.

    Args:
        conn: An active DuckDB connection.

    Returns:
        A dictionary mapping secret names to their properties.
    """
    secrets = conn.execute("SELECT name, secret_string FROM duckdb_secrets()").fetchall()
    return {name: parse_secret_string(secret_string) for name, secret_string in secrets}


def parse_secret_string(secret_string: str) -> dict[str, str]:
    """Parse the given DuckDB secret string into its parts.

    Args:
        secret_string: The string to parse.

    Returns:
        A dictionary mapping each part's name to its value.
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
