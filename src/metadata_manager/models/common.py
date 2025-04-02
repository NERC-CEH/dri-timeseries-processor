from typing import Any, List

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
