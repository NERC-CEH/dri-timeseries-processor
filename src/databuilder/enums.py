from enum import StrEnum


class Operator(StrEnum):
    """List of valid operators"""

    GREATER_THAN = ">"
    GREATER_THAN_EQUAL = ">="
    LESS_THAN = "<"
    LESS_THAN_EQUAL = "<="
    EQUAL = "=="
