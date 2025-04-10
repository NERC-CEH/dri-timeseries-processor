from typing import Any, Dict, List, Tuple

# To get the last bit of a uri string, after the last trailing slash.
#   Allows for alpha characters, underscore and hyphen.
#   e.g. http://fdri.ceh.ac.uk/ref/cosmos/time-series/lwin_raw => lwin_raw
URI_ID_EXTRACT_REGEX = r".+\/([a-zA-Z0-9\-\_]+)$"

# To get the last bit of the site ID.
#   e.g. http://fdri.ceh.ac.uk/id/site/cosmos-chimn => chimn
SITE_ID_EXTRACT_REGEX = r".+\/\w+\-([a-zA-Z0-9]+)$"


def check_single_list_item(data: List) -> Any:
    """Checks that list has a single item within in.
    Args:
        data: List to check
    Returns:
        The first item of the list
    """
    if isinstance(data, list):
        num_items = len(data)
        if num_items != 1:
            raise ValueError(f"Single list check failed. {num_items} items found: {data}")
        data = data[0]
    return data


def get_property(key: str, prop: Dict[str, Any] | None) -> Any:
    """
    Given a dict like {key: [a,b,c]}, the first value of the list will be returned
    Given a dict like {key: a}, a will be returned

    Args:
        key: the key to look for
        prop: the dict to search in.

    Returns:
        The value associated with the key.
    """
    if not prop:
        return None

    values = prop.get(key)
    if isinstance(values, list):
        return values[0]

    return values


def build_site_query_parameter(sites: List[str]) -> List[Tuple]:
    """Build the site query parameters for the dataset endpoint.

    As we use the same key for multiple sites, it needs to be a list of tuples.

    Args:
        sites: A list of the sites to query.

    Returns:
        A list of tuples with query parameter string and site.
    """
    return [("originatingSite", f"http://fdri.ceh.ac.uk/id/site/cosmos-{site.lower()}") for site in sites]


def build_column_query_parameter(columns: List[str]) -> List[Tuple]:
    """Build the column name query parameters for the dataset endpoint.

    As we use the same key for multiple columns, it needs to be a list of tuples.

    Args:
        columns: The column names to query.

    Returns:
        A list of tuples with query parameter string and column name.
    """
    return [("sourceColumnName", column) for column in columns]


def build_periodicity_query_parameter(periodicities: List[str]) -> List[Tuple]:
    """Build the periodicity query parameters for the dataset endpoint.

    As we use the same key for multiple periods, it needs to be a list of tuples.

    Args:
        periodicities: A list of the periodicities to query.

    Returns:
        A list of tuples with query parameter string and period.
    """
    return [("type.measure.aggregation.periodicity", period) for period in periodicities]
