"""
Config for core flags
This is a placeholder while a proper metadata store is being built.

The configs are built using dictionaries (update these when adding to them) and
validated with Pydantic.

"""

import json
from pathlib import Path

from pydantic import BaseModel, field_validator


class CoreFlag(BaseModel):
    """
    Info on a core flag

    Attributes:
        name (str): The name of the flag
        description (str): Description of the flag
        symbol (List[str]): A short string symbol for the flag.
        id (int): Flag ID value.
    """

    name: str
    description: str
    symbol: str
    id: int

    @field_validator("id")
    def check_id(cls, v: float) -> float:
        """
        Validates that the id is a power of 2

        Args:
            cls (Type[CoreFlag]): The class of the model being validated.
            v (float): The value of id to validate.

        Raises:
            ValueError: If id is not even

        Returns:
            float: The validated id.
        """
        # Use bit manipulation &, to determine power of 2.
        # Power of 2 is always 1 followed by 0's e.g. 8 == 1000
        # Minus 1 of power of 2 is 0 followed by 1's, e.g. 7 == 0111
        # Therefore the & operation results in 0. e.g. 8 & 7 == 0000
        if not ((v & (v - 1) == 0) and v != 0):
            raise ValueError("id must be a power of 2")
        return v


# Instantiate the models
with open(Path(__file__).parent / "config_files" / "core_flags.json", "r") as f:
    content = json.load(f)

    core_flags = content["core_flags"]
    core_flag_config = {flag: CoreFlag(**info) for flag, info in core_flags.items()}

    del content
