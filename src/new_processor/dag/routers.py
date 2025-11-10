from typing import Any

from driutils.metadata_api.api_manager import MetadataAPIManager


class MetadataRouter:
    """Route metadata API requests to the correct network-specific manager."""

    def __init__(self, host: str, network: str):
        self.host = host
        self.client = MetadataAPIManager(host=self.host, network=network)

    async def fetch_dataset_by_params(self, query_params: list[tuple[str, str]]) -> dict[str, Any]:
        url = f"{self.host}/id/dataset"
        return await self.client._make_paginated_api_call(url, query_params)

    async def fetch_dataset_by_id(self, dataset_id: str) -> dict[str, Any]:
        url = f"{self.host}/id/dataset/{dataset_id}?_view=timeseries"
        return await self.client._make_paginated_api_call(url)

    async def fetch_all_dependencies(self, dataset_id: str) -> dict[str, Any]:
        url = f"{self.host}/id/dataset/{dataset_id}/_all_dependencies"
        return await self.client._make_paginated_api_call(url)
