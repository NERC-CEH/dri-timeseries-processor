from pydantic import BaseModel, field_validator


class CoreFlagItem(BaseModel):
    """
    Info on a core flag
    """

    name: str
    description: str
    id: int

    @field_validator("id")
    def check_id(cls, v: int) -> int:
        """
        Validates that the id is a power of 2

        Args:
            cls (Type[CoreFlag]): The class of the model being validated.
            v (integer): The value of id to validate.

        Raises:
            ValueError: If id is not even

        Returns:
            float: The validated id.
        """
        if not isinstance(v, int):
            raise ValueError("id must be an integer")
        # Use bit manipulation &, to determine power of 2.
        # Power of 2 is always 1 followed by 0's e.g. 8 == 1000
        # Minus 1 of power of 2 is 0 followed by 1's, e.g. 7 == 0111
        # Therefore the & operation results in 0. e.g. 8 & 7 == 0000
        if not ((v & (v - 1) == 0) and v != 0):
            raise ValueError("id must be a power of 2")
        return v


class CoreFlagResponse(BaseModel):
    """Container for all core flag definitions.
    JSON root contains: {"core_flags": {...}}
    """

    core_flags: dict[str, CoreFlagItem]
