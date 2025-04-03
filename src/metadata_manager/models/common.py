from typing import Dict, Any

# To get the last bit of a uri string, after the last trailing slash.
#   Allows for alpha characters, underscore and hyphen.
#   e.g. http://fdri.ceh.ac.uk/ref/cosmos/time-series/lwin_raw => lwin_raw
URI_ID_EXTRACT_REGEX = r".+\/([a-zA-Z0-9\-\_]+)$"

# To get the last bit of the site ID.
#   e.g. http://fdri.ceh.ac.uk/id/site/cosmos-chimn => chimn
SITE_ID_EXTRACT_REGEX = r".+\/\w+\-([a-zA-Z0-9]+)$"

def build_site_query_parameter(sites):
    """"""
    sites_params = []
    for site in sites:
        sites_params.append(('originatingSite', f"http://fdri.ceh.ac.uk/id/site/cosmos-{site}"))
    return sites_params


def get_property(key: str, prop: Dict[str, Any] | None) -> Any:
    """
    Given a dict like {key: [a,b,c]}, the first value of the list will be returned
    Given a dict like {key: a}, a will be returned
    """
    if not prop:
        return None
    values = prop.get(key)
    if isinstance(values, list):
        return values[0]
    return values