INFILL_META_INTERNAL_COL = "__INFILL_META__"


def infill_meta_column_name(column: str) -> str:
    """
    Return column name of infill metadata column for a given variable column.

    Args:
        column: Data column name

    Returns:
        Metadata column name
    """
    return f"{column}_INFILL_META"
