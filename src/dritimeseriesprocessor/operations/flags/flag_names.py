def core_flag_column_name(column: str) -> str:
    """Return flag column name for given data column name.

    Args:
        column: Data column name

    Returns:
        Flag column name
    """
    return f"{column}_CORE_FLAG"


def corrs_flag_column_name(column: str) -> str:
    """
    Return column name of corrections flag column for a given variable column.

    Args:
        column: Data column name

    Returns:
        Flag column name
    """
    return f"{column}_CORRS_FLAG"


def qc_flag_column_name(column: str) -> str:
    """
    Return column name of QC flag column for a given variable column.

    Args:
        column: Data column name

    Returns:
        Flag column name
    """
    return f"{column}_QC_FLAG"


def infill_flag_column_name(column: str) -> str:
    """
    Return column name of infill flag column for a given variable column.

    Args:
        column: Data column name

    Returns:
        Flag column name
    """
    return f"{column}_INFILL_FLAG"
