from enum import StrEnum


class Operators(StrEnum):
    """List of valid operators"""

    GREATER_THAN = ">"
    GREATER_THAN_EQUAL = ">="
    LESS_THAN = "<"
    LESS_THAN_EQUAL = "<="
    EQUAL = "=="
