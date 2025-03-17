# To get the last bit of a uri string, after the last trailing slash.
#   Allows for alpha characters, underscore and hyphen.
#   e.g. http://fdri.ceh.ac.uk/ref/cosmos/time-series/lwin_raw => lwin_raw
URI_ID_EXTRACT_REGEX = r".+\/([a-zA-Z0-9\-\_]+)$"

# To get the last bit of the site ID.
#   e.g. http://fdri.ceh.ac.uk/id/site/cosmos-chimn => chimn
SITE_ID_EXTRACT_REGEX = r".+\/\w+\-([a-zA-Z0-9]+)$"
