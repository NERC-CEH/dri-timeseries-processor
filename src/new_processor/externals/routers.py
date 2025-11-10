from typing import Any

from new_processor.externals.api_manager import MetadataAPIManager


class MetadataRouter:
    """Route metadata API requests to the correct network-specific manager."""

    def __init__(self, host: str):
        self.host = host
        self.api_manager = MetadataAPIManager(host=self.host)

    def fetch_dataset_by_params(self, query_params: tuple[tuple[str, str], ...]) -> dict[str, Any]:
        url = f"{self.host}/id/dataset"
        print(url, query_params)
        return self.api_manager._make_paginated_api_call(url, query_params)

    def fetch_dataset_by_id(self, dataset_id: str) -> dict[str, Any]:
        url = f"{self.host}/id/dataset/{dataset_id}?_view=timeseries"
        print(url)
        return self.api_manager._make_paginated_api_call(url)

    def fetch_all_dependencies(self, dataset_id: str) -> dict[str, Any]:
        url = f"{self.host}/id/dataset/{dataset_id}/_all_dependencies"
        print(url)
        return self.api_manager._make_paginated_api_call(url)

    def fetch_processing_configs(self, query_params: tuple[tuple[str, str], ...]) -> dict[str, Any]:
        url = f"{self.host}/id/data-processing-configuration"
        print(url, query_params)
        return self.api_manager._make_paginated_api_call(url, query_params)
