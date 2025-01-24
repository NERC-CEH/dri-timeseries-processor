"""
Config required for infilling
This is a placeholder while a proper metadata store is being built.

The configs are built using dictionaries (update these when adding to them) and
validated with Pydantic.

"""

import json
from pathlib import Path
from typing import Dict, List, Literal, Union

from pydantic import (
    BaseModel,
    model_validator,
)


class InfillMethod(BaseModel):
    name: str
    description: str
    requirements: dict
    id: int


class Method(BaseModel):
    method: str
    priority: int
    constraints: dict

    @model_validator(mode="after")
    def validate_method(cls, v: "Method") -> "Method":
        if v.method not in infill_methods:
            raise ValueError(f"Invalid method: {v.method}. Must be one of {list(infill_methods.keys())}")
        return v


class VariableResolutionMethods(BaseModel):
    methods: List[Method]

    @model_validator(mode="after")
    def check_unique_priorities(cls, var_res: "VariableResolutionMethods") -> "VariableResolutionMethods":
        priorities = [method.priority for method in var_res.methods]
        if len(priorities) != len(set(priorities)):
            raise ValueError("All method priorities must be unique")
        return var_res


def get_infill_config(
    config: Literal["infill_methods", "variables"],
) -> Union[Dict[str, InfillMethod], Dict[str, Dict[str, VariableResolutionMethods]]]:
    """
    Retrieve infill configuration based on the specified config type.

    Args:
        config: The type of configuration to retrieve.
            Must be either "infill_methods" or "variables".

    Returns:
        For "infill_methods": A dictionary mapping method names to InfillMethod objects.
        For "variables": A nested dictionary. The outer dictionary maps variable names
        to inner dictionaries, which in turn map resolution names to VariableResolutionMethods objects.

    Raises:
        ValueError: If an invalid config type is provided.
    """
    if config == "infill_methods":
        infl_config = {method: InfillMethod(**info) for method, info in infill_methods.items()}
    elif config == "variables":
        infl_config = {}
        for var, var_res_dict in variables.items():
            infl_config[var] = var_res_dict
            for res, res_methods in var_res_dict.items():
                infl_config[var][res] = VariableResolutionMethods(**res_methods)
    else:
        raise ValueError("Not a valid config type")

    return infl_config


# Instantiate the models
with open(Path(__file__).parent / "config_files" / "infilling.json", "r") as f:
    content = json.load(f)

    infill_methods = content["infill_methods"]
    variables = content["variables"]

    del content
