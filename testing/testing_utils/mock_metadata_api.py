from collections import defaultdict
from typing import Any, Dict, Generator, List, Tuple


class MockMetadataAPI:
    def __init__(self, api_data: Dict[str, Any]):
        """
        Mock metadata API service designed to replace _make_api_call in MetadataAPIManager via a mock side effect.
        The data stored in api_data is used as a database of api response values. The structure is expected to be:

            {url: dictionary of metadata responses for the url}

        Default values for the api_data can be found in TestHelper.metadata_api_data

        Args:
            api_data (Dict[str, Any]): Dictionary of data used to extract metadata responses

        """
        self.api_data = api_data

        self.filter_func_mapping = {
            "@id": filter_by_id,
            "originatingSite": filter_by_site,
            "type.measure.aggregation.periodicity": filter_by_periodicity,
            "sourceColumnName": filter_by_column,
            "type.processingLevel": filter_by_processing_level,
            "type": filter_by_type,
        }

    def __call__(self, url: str, params: Dict[str, str] | List[Tuple[str, str]] = None):
        """Main call function, designed to replace _make_api_call in MetadataAPIManager via a mock side effect."""
        if params is None:
            return self.api_data[url]

        return self.filter_data(url, params)

    def filter_data(self, url: str, params: Dict[str, str] | List[Tuple[str, str]]) -> Dict[str, Any]:
        """Filter api_data by the provided url and parameters."""
        filtered_data = self.api_data[url]["items"].copy()
        for param_key, param_value in params_iterator(params):
            filter_func = self.filter_func_mapping.get(param_key)
            if not filter_func:
                continue

            filtered_data = filter_func(param_value, filtered_data)

        return {"meta": self.api_data[url]["meta"], "items": filtered_data}


def params_iterator(params: Dict[str, str] | List[Tuple[str, str]]) -> Generator[Tuple[str, str], Any, Any]:
    """
    Generator to iterate over the provided params object

    In order for the various filter functions to have consistent logic and input expectations, the parameters are
    converted to the format of Dict[str: List[str]] to allow filtering on multiple possible parameter values (e.g.
    multiple sites, or variable column names)

    """
    if isinstance(params, list):
        params_dict = convert_params_to_dict(params)
    else:
        params_dict = {}
        for key, value in params.items():
            params_dict[key] = value if (isinstance(value, list)) else [value]

    yield from params_dict.items()


def convert_params_to_dict(params: List[Tuple[str, str]]) -> Dict[str, List[str]]:
    """Convert the parameters to a standardised format.

    In order for the various filter functions to have consistent logic and input expectations, the parameters are
    converted to the format of Dict[str: List[str]] to allow filtering on multiple possible parameter values (e.g.
    multiple sites, or variable column names)
    """
    params_dict = defaultdict(list)
    for key, value in params:
        params_dict[key].append(value)

    return params_dict


def filter_by_id(param_values: List[str], api_data: Dict[str, Any]) -> Dict[str, Any]:
    """Filter the api_data by metadata id."""
    filtered_data = [item for item in api_data if item["@id"] in param_values]
    return filtered_data


def filter_by_site(param_values: List[str], api_data: Dict[str, Any]) -> Dict[str, Any]:
    """Filter the api_data by one or more site ids."""
    filtered_data = [item for item in api_data if item["originatingSite"][0]["@id"] in param_values]
    return filtered_data


def filter_by_periodicity(param_values: List[str], api_data: Dict[str, Any]) -> Dict[str, Any]:
    """Filter the api_data by one or more periodicity ids."""
    filtered_data = [
        item for item in api_data if item["type"][0]["measure"]["aggregation"]["periodicity"] in param_values
    ]
    return filtered_data


def filter_by_column(param_values: List[str], api_data: Dict[str, Any]) -> Dict[str, Any]:
    """Filter the api_data by one or more column names."""
    filtered_data = [item for item in api_data if item.get("sourceColumnName") in param_values]
    return filtered_data


def filter_by_processing_level(param_values: List[str], api_data: Dict[str, Any]) -> Dict[str, Any]:
    """Filter the api_data by one or more processing level ids."""
    filtered_data = [item for item in api_data if item["type"][0]["processingLevel"]["@id"] in param_values]
    return filtered_data


def filter_by_type(param_values: List[str], api_data: Dict[str, Any]) -> Dict[str, Any]:
    """Filter the api_data by one or more type ids."""
    filtered_data = [item for item in api_data if item["type"][0]["@id"] in param_values]
    return filtered_data
