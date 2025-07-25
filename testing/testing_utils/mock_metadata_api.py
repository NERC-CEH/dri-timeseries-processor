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
            api_data: Dictionary of data used to extract metadata responses

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
        """
        Main call function, designed to replace _make_api_call in MetadataAPIManager via a mock side effect.

        Args:
            url: The url to query against self.api_data to identify data to be returned
            params: Query parameters to use for filtering the mock api response. Defaults to None.

        Returns:
            Dict[str, Any]: Dictionary containing the filtered metadata value(s) from self.api_data. The contents should
                be a direct match for the equivalent API call to the main metadata api.

        """
        if params is None:
            return self.api_data[url]

        return self.filter_data(url, params)

    def filter_data(self, url: str, params: Dict[str, str] | List[Tuple[str, str]]) -> Dict[str, Any]:
        """
        Filter self.api_data by the provided url and parameters as if the main metadata api was processing a query
        with parameters.

        Due to the nested structure of the metadata api's data, and corresponding query parameeter keys
        (e.g. type.measure.aggregation.periodicity, custom filter functions per parameter key are used. If the parameter
        key does not have a corresponding filter function, it is skipped (e.g. `_view` or `_limit`).

        Args:
            url: The intial key to use to extract the relevant api data to filter.
            params: Parameters to filter by.

        Returns:
            Dict[str, Any]: Dictionary containing the filtered metadata value(s) from self.api_data. The contents should
                be a direct match for the equivalent API call to the main metadata api.
        """
        filtered_data = self.api_data[url]["items"].copy()
        for param_key, param_value in params_iterator(params):
            filter_func = self.filter_func_mapping.get(param_key)
            if not filter_func:
                continue

            filtered_data = filter_func(param_value, filtered_data)

        return {"meta": self.api_data[url]["meta"], "items": filtered_data}


def params_iterator(params: Dict[str, str] | List[Tuple[str, str]]) -> Generator[Tuple[str, str], Any, Any]:
    """
    Generator to iterate over the provided params object.

    Args:
        params: Dictionary, or tuple containing the query parameters

    Yields:
        Tuple[str, str]: Tuple of a single entry from the reformatted params object containing the parameter_key and
            list of parameter_values to filter the api dictionary based response by.

    """
    if isinstance(params, list):
        params_dict = convert_params_to_dict(params)
    else:
        params_dict = {}
        for key, value in params.items():
            params_dict[key] = value if (isinstance(value, list)) else [value]

    yield from params_dict.items()


def convert_params_to_dict(params: List[Tuple[str, str]]) -> Dict[str, List[str]]:
    """Reformat the parameters to a standardised dictionary based structure.

    In order for the various filter functions to have consistent logic and input expectations, the parameters are
    converted to the format of {parameter key, [parameter value 1, parameter value 2]} to allow filtering on
    multiple possible parameter values (e.g. multiple sites, or variable column names).

    Args:
        params: List of tuples in the format of (parameter key, parameter value)

    Returns:
        Dict[str, List[str]]: Reformatted parameters.

    """
    params_dict = defaultdict(list)
    for key, value in params:
        params_dict[key].append(value)

    return params_dict


def filter_by_id(param_values: List[str], api_data: Dict[str, Any]) -> Dict[str, Any]:
    """Filter the api_data by one or more metadata id.

    Iterate through the provided api data searching for any entries which have a matching @id to any of the values in
    the provided parameter values list.

    Args:
        param_values: List of values to search for within the provided api data
        api_data (Dict[str, Any]): Dictionary of api data to filter. This is provided rather than using self.api_data
            to allow nested filtering (e.g. filter by id and by site)

    Returns:
        Dict[str, Any]: Dictionary containing the filtered metadata value(s) from self.api_data. The contents should
            be a direct match for the equivalent API call to the main metadata api.

    """
    filtered_data = [item for item in api_data if item["@id"] in param_values]
    return filtered_data


def filter_by_site(param_values: List[str], api_data: Dict[str, Any]) -> Dict[str, Any]:
    """Filter the api_data by one or more site ids.

    Iterate through the provided api data searching for any entries which have a matching originatingSite @id value to
    any of the values in the provided parameter values list.

    Args:
        param_values: List of values to search for within the provided api data
        api_data (Dict[str, Any]): Dictionary of api data to filter. This is provided rather than using self.api_data
            to allow nested filtering (e.g. filter by id and by site)

    Returns:
        Dict[str, Any]: Dictionary containing the filtered metadata value(s) from self.api_data. The contents should
            be a direct match for the equivalent API call to the main metadata api.

    """
    filtered_data = [item for item in api_data if item["originatingSite"][0]["@id"] in param_values]
    return filtered_data


def filter_by_periodicity(param_values: List[str], api_data: Dict[str, Any]) -> Dict[str, Any]:
    """Filter the api_data by one or more site ids.

    Iterate through the provided api data searching for any entries which have a matching periodicity code (e.g. PT30M)
    to any of the values in the provided parameter values list. The periodicity code is located deeply nested within the
    main `type` section of a metadata api item. It is assumed that only the first item within the `type` list is 
    relevant for filtering purposes.

    Args:
        param_values: List of values to search for within the provided api data
        api_data (Dict[str, Any]): Dictionary of api data to filter. This is provided rather than using self.api_data
            to allow nested filtering (e.g. filter by id and by site)

    Returns:
        Dict[str, Any]: Dictionary containing the filtered metadata value(s) from self.api_data. The contents should
            be a direct match for the equivalent API call to the main metadata api.

    """
    filtered_data = [
        item for item in api_data if item["type"][0]["measure"]["aggregation"]["periodicity"] in param_values
    ]
    return filtered_data


def filter_by_column(param_values: List[str], api_data: Dict[str, Any]) -> Dict[str, Any]:
    """Filter the api_data by one or more column names.

    Iterate through the provided api data searching for any entries which have a matching sourceColumnName value to
    any of the values in the provided parameter values list.

    Args:
        param_values: List of values to search for within the provided api data
        api_data (Dict[str, Any]): Dictionary of api data to filter. This is provided rather than using self.api_data
            to allow nested filtering (e.g. filter by id and by site)

    Returns:
        Dict[str, Any]: Dictionary containing the filtered metadata value(s) from self.api_data. The contents should
            be a direct match for the equivalent API call to the main metadata api.

    """
    filtered_data = [item for item in api_data if item.get("sourceColumnName") in param_values]
    return filtered_data


def filter_by_processing_level(param_values: List[str], api_data: Dict[str, Any]) -> Dict[str, Any]:
    """Filter the api_data by one or more processing level ids.

    Iterate through the provided api data searching for any entries which have a matching processingLevel @id attribute
    to any of the values in the provided parameter values list. The processingLevel @id attribute is located deeply 
    nested within the main `type` section of a metadata api item. It is assumed that only the first item within the 
    `type` list is relevant for filtering purposes.

    Args:
        param_values: List of values to search for within the provided api data
        api_data (Dict[str, Any]): Dictionary of api data to filter. This is provided rather than using self.api_data
            to allow nested filtering (e.g. filter by id and by site)

    Returns:
        Dict[str, Any]: Dictionary containing the filtered metadata value(s) from self.api_data. The contents should
            be a direct match for the equivalent API call to the main metadata api.

    """
    filtered_data = [item for item in api_data if item["type"][0]["processingLevel"]["@id"] in param_values]
    return filtered_data


def filter_by_type(param_values: List[str], api_data: Dict[str, Any]) -> Dict[str, Any]:
    """Filter the api_data by one or more type ids.

    Iterate through the provided api data searching for any entries which have a matching type @id attribute to
    any of the values in the provided parameter values list. It is assumed that only the first item within the 
    `type` list is relevant for filtering purposes.

    Args:
        param_values: List of values to search for within the provided api data
        api_data (Dict[str, Any]): Dictionary of api data to filter. This is provided rather than using self.api_data
            to allow nested filtering (e.g. filter by id and by site)

    Returns:
        Dict[str, Any]: Dictionary containing the filtered metadata value(s) from self.api_data. The contents should
            be a direct match for the equivalent API call to the main metadata api.

    """
    filtered_data = [item for item in api_data if item["type"][0]["@id"] in param_values]
    return filtered_data
