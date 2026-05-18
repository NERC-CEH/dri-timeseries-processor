from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from dritimeseriesprocessor import PACKAGE_ROOT
from dritimeseriesprocessor.models.api_models.data_processing_configuration import DataProcessingConfiguration
from dritimeseriesprocessor.models.api_models.dataset_observation import ObservationDatasetResponse
from dritimeseriesprocessor.models.api_models.dataset_timeseries import TimeSeriesDatasetResponse
from dritimeseriesprocessor.models.api_models.network import Network
from dritimeseriesprocessor.models.api_models.site import SiteResponse
from dritimeseriesprocessor.utils.strings import extract_uri_id

_FLAT_TYPE_TO_URI = {
    "fdri:ObservationDataset": "http://fdri.ceh.ac.uk/vocab/metadata/ObservationDataset",
    "fdri:TimeSeriesDataset": "http://fdri.ceh.ac.uk/vocab/metadata/TimeSeriesDataset",
}
_DEFAULT_TYPE_URI = "http://fdri.ceh.ac.uk/vocab/metadata/TimeSeriesDataset"


def _identifier_aliases(*values: str | None) -> set[str]:
    aliases: set[str] = set()
    for value in values:
        if not value:
            continue
        aliases.add(value)
        if "/" in value:
            aliases.add(extract_uri_id(value))
    return aliases


@dataclass(frozen=True)
class EddyProFixtureSet:
    network: Network
    sites: SiteResponse
    observation_datasets: ObservationDatasetResponse
    timeseries_datasets: TimeSeriesDatasetResponse
    processing_configs: DataProcessingConfiguration


class LocalEddyProMetadataSource:
    """Read the local EddyPro fixtures and validate them."""

    METADATA_DIR = PACKAGE_ROOT / "__metadata__" / "eddypro"

    def __init__(self, network: str, sites: list[str] | None = None) -> None:
        self._network = network
        self._requested_sites = set(sites or [])

    def load(self) -> EddyProFixtureSet:
        network_data = self._read_json("network.json")
        if network_data["id"] != self._network:
            raise FileNotFoundError(f"Local EddyPro metadata fixture not found for network: {self._network}")

        sites_data = self._read_json("sites.json")
        datasets_data = self._read_json("datasets.json")
        processing_configs_data = self._read_json("processing_configs.json")

        sites = self._build_site_response(sites_data, network_data["id"])
        network = self._build_network_response(network_data, sites_data)
        obs_datasets = self._build_observation_dataset_response(datasets_data)
        ts_datasets = self._build_timeseries_dataset_response(datasets_data)
        processing_configs = self._build_processing_config_response(processing_configs_data, obs_datasets, ts_datasets)

        filtered_sites = self._filter_sites(sites)
        filtered_network = self._filter_network(network, filtered_sites)
        filtered_obs_datasets = self._filter_observation_datasets(obs_datasets, filtered_sites)
        filtered_ts_datasets = self._filter_timeseries_datasets(ts_datasets, filtered_sites)
        filtered_processing_configs = self._filter_processing_configs(
            processing_configs, filtered_obs_datasets, filtered_ts_datasets
        )

        return EddyProFixtureSet(
            network=filtered_network,
            sites=filtered_sites,
            observation_datasets=filtered_obs_datasets,
            timeseries_datasets=filtered_ts_datasets,
            processing_configs=filtered_processing_configs,
        )

    def _build_network_response(self, network_data: dict[str, Any], sites_data: dict[str, Any]) -> Network:
        site_items: list[dict[str, Any]] = []
        for site_ref in network_data.get("sites", []):
            site = self._find_site(site_ref, sites_data.get("sites", []))
            if site is None:
                continue
            site_items.append(
                {
                    "@id": site["site_id"],
                    "label": [site.get("full_name") or site.get("alt_id") or site_ref],
                }
            )

        payload = {
            "meta": self._meta_dict(),
            "items": [
                {
                    "@id": f"http://fdri.ceh.ac.uk/id/network/{network_data['id']}",
                    "@type": [
                        {
                            "@id": "http://fdri.ceh.ac.uk/vocab/metadata/EnvironmentalMonitoringNetwork",
                        }
                    ],
                    "label": [network_data.get("label") or f"{network_data['id'].upper()} network"],
                    "contains": site_items,
                }
            ],
        }
        return Network.model_validate(payload)

    def _build_site_response(self, sites_data: dict[str, Any], network_id: str) -> SiteResponse:
        items = []
        for site in sites_data.get("sites", []):
            identifiers = list(site.get("identifiers") or [])
            if site.get("alt_id") and site["alt_id"] not in identifiers:
                identifiers.append(site["alt_id"])

            items.append(
                {
                    "@id": site["site_id"],
                    "@type": [
                        {
                            "@id": "http://fdri.ceh.ac.uk/vocab/metadata/EnvironmentalMonitoringSite",
                        }
                    ],
                    "identifier": identifiers,
                    "label": [site.get("full_name") or site.get("alt_id") or site["site_id"]],
                    "easting": site.get("easting"),
                    "northing": site.get("northing"),
                    "lat": site.get("lat"),
                    "long": site.get("lon"),
                    "altitude": site.get("altitude"),
                    "operatingPeriod": {
                        "@id": f"{site['site_id']}/operating-period",
                        "startDate": site.get("start_date") or "2024-01-01T00:00:00Z",
                        "endDate": site.get("end_date"),
                    },
                    "utilisedBy": [
                        {
                            "@id": f"http://fdri.ceh.ac.uk/id/programme/{site.get('network') or network_id}",
                            "label": [f"{(site.get('network') or network_id).upper()} programme"],
                        }
                    ],
                }
            )

        return SiteResponse.model_validate({"meta": self._meta_dict(), "items": items})

    def _build_dataset_item(self, dataset: dict[str, Any]) -> dict[str, Any]:
        variable_id = dataset["dataset_id"].rsplit("/", 1)[-1]
        variable_uri = (
            variable_id
            if variable_id.startswith("http://")
            else f"http://fdri.ceh.ac.uk/ref/common/variable/{variable_id}"
        )
        unit_id = dataset.get("unit_id") or "not-applicable"
        unit_uri = unit_id if unit_id.startswith("http://") else f"http://fdri.ceh.ac.uk/ref/common/unit/{unit_id}"

        return {
            "@id": dataset["dataset_id"],
            "@type": [
                {
                    "@id": _FLAT_TYPE_TO_URI.get(dataset.get("@type", ""), _DEFAULT_TYPE_URI),
                }
            ],
            "processingLevel": {
                "@id": f"http://fdri.ceh.ac.uk/ref/common/processing-level/{dataset['processing_level']}",
            },
            "measure": [
                {
                    "@id": f"http://fdri.ceh.ac.uk/id/measure/{dataset['dataset_id'].rsplit('/', 1)[-1]}",
                    "variable": {
                        "@id": variable_uri,
                        "prefLabel": [variable_id],
                    },
                    "hasUnit": {
                        "@id": unit_uri,
                        "prefLabel": [dataset.get("unit_label") or "not applicable"],
                    },
                    "aggregation": {
                        "@id": (
                            dataset.get("aggregation_id")
                            or "http://fdri.ceh.ac.uk/ref/common/aggregation/"
                            f"{dataset['dataset_id'].rsplit('/', 1)[-1]}"
                        ),
                        "periodicity": dataset["periodicity"],
                        "resolution": dataset["resolution"],
                    },
                }
            ],
            "sourceBucket": dataset.get("source_bucket"),
            "sourceDataset": dataset.get("source_dataset"),
            "sourceColumnName": dataset.get("source_column"),
            "sourceTimeColumnName": dataset.get("time_column_name"),
            "distribution": (
                [
                    {
                        "@id": f"http://fdri.ceh.ac.uk/id/distribution/{dataset['dataset_id'].rsplit('/', 1)[-1]}",
                        "accessUrl": dataset["distribution"],
                    }
                ]
                if dataset.get("distribution")
                else None
            ),
            "originatingFacility": [{"@id": dataset["platform_id"]}] if dataset.get("platform_id") else [],
            "originatingSite": [{"@id": dataset["site_id"]}],
            "originatingProgramme": [
                {
                    "@id": f"http://fdri.ceh.ac.uk/id/programme/{dataset['network']}",
                }
            ],
        }

    def _build_observation_dataset_response(self, datasets_data: dict[str, Any]) -> ObservationDatasetResponse:
        items = [
            self._build_dataset_item(d)
            for d in datasets_data.get("datasets", [])
            if d.get("@type") == "fdri:ObservationDataset"
        ]
        return ObservationDatasetResponse.model_validate({"meta": self._meta_dict(), "items": items})

    def _build_timeseries_dataset_response(self, datasets_data: dict[str, Any]) -> TimeSeriesDatasetResponse:
        items = [
            self._build_dataset_item(d)
            for d in datasets_data.get("datasets", [])
            if d.get("@type") != "fdri:ObservationDataset"
        ]
        return TimeSeriesDatasetResponse.model_validate({"meta": self._meta_dict(), "items": items})

    def _build_processing_config_response(
        self,
        configs_data: dict[str, Any],
        observation_datasets: ObservationDatasetResponse,
        timeseries_datasets: TimeSeriesDatasetResponse,
    ) -> DataProcessingConfiguration:
        all_items = list(observation_datasets.items) + list(timeseries_datasets.items)
        dataset_site_map = {item.id: item.originating_site[0].id for item in all_items if item.originating_site}
        items = []

        for config in configs_data.get("processing_configs", []):
            config_id = config["config_id"]
            applies_to_dataset = config["applies_to_dataset"]
            site_id = config.get("site_id") or dataset_site_map[applies_to_dataset]
            items.append(
                {
                    "@id": f"http://fdri.ceh.ac.uk/id/data-processing-configuration/{config_id}",
                    "@type": [
                        {
                            "@id": "http://fdri.ceh.ac.uk/vocab/metadata/InternalDataProcessingConfiguration",
                        }
                    ],
                    "type": {
                        "@id": f"http://fdri.ceh.ac.uk/ref/common/configuration-type/{config['config_type']}",
                    },
                    "appliesToDataset": [
                        {
                            "@id": applies_to_dataset,
                            "originatingSite": [{"@id": site_id}],
                        }
                    ],
                    "hasCurrentValue": [
                        {
                            "@id": f"http://fdri.ceh.ac.uk/id/configuration-item/{config_id}-current",
                            "@type": [
                                {
                                    "@id": "http://fdri.ceh.ac.uk/vocab/metadata/ConfigurationItem",
                                }
                            ],
                            "method": {
                                "@id": f"http://fdri.ceh.ac.uk/ref/common/processing-method/{config['method']}",
                            },
                            "observationInterval": {
                                "@id": f"http://fdri.ceh.ac.uk/id/period/{config_id}-current",
                                "@type": [
                                    {
                                        "@id": "http://purl.org/dc/terms/PeriodOfTime",
                                    }
                                ],
                                "startDate": config.get("start_date") or "2024-01-01T00:00:00Z",
                                "endDate": config.get("end_date"),
                            },
                            "argument": self._build_argument_items(config.get("params") or {}, config_id),
                        }
                    ],
                }
            )

        return DataProcessingConfiguration.model_validate({"meta": self._meta_dict(), "items": items})

    def _build_argument_items(self, params: dict[str, Any], base_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for param_name, value in params.items():
            items.extend(self._build_argument_item_list(param_name, value, f"{base_id}/{param_name}"))
        return items

    def _build_argument_item_list(self, param_name: str, value: Any, base_id: str) -> list[dict[str, Any]]:
        if value is None:
            return []

        if isinstance(value, dict):
            return [self._build_structured_argument(param_name, value, base_id)]

        if isinstance(value, list):
            if not value:
                return []
            if all(isinstance(item, dict) for item in value):
                return [
                    self._build_structured_argument(param_name, item, f"{base_id}/{index}")
                    for index, item in enumerate(value, start=1)
                ]
            if param_name == "dep_ts":
                return [self._build_value_argument(param_name, value, base_id, as_reference=True)]
            return [
                self._build_value_argument(param_name, item, f"{base_id}/{index}")
                for index, item in enumerate(value, start=1)
            ]

        return [
            self._build_value_argument(
                param_name,
                value,
                base_id,
                as_reference=param_name == "dep_ts",
            )
        ]

    def _build_structured_argument(self, param_name: str, value: dict[str, Any], base_id: str) -> dict[str, Any]:
        return {
            "@id": f"http://fdri.ceh.ac.uk/id/config-arg/{base_id}",
            "parameter": {
                "@id": self._parameter_uri(param_name),
            },
            "hasStructuredValue": {
                "@id": f"http://fdri.ceh.ac.uk/id/config-arg-list/{base_id}",
                "argument": self._build_argument_items(value, base_id),
            },
        }

    def _build_value_argument(
        self,
        param_name: str,
        value: Any,
        base_id: str,
        as_reference: bool = False,
    ) -> dict[str, Any]:
        has_value: dict[str, Any] = {
            "@id": f"http://fdri.ceh.ac.uk/id/config-value/{base_id}",
        }
        if as_reference:
            if isinstance(value, list):
                has_value["valueReference"] = [{"@id": ref} for ref in value]
            else:
                has_value["valueReference"] = {"@id": value}
        else:
            has_value["value"] = [value]

        return {
            "@id": f"http://fdri.ceh.ac.uk/id/config-arg/{base_id}",
            "parameter": {
                "@id": self._parameter_uri(param_name),
            },
            "hasValue": has_value,
        }

    @staticmethod
    def _parameter_uri(param_name: str) -> str:
        return f"http://fdri.ceh.ac.uk/ref/common/configuration-parameter/{param_name.replace('_', '-')}"

    @staticmethod
    def _find_site(site_ref: str, sites: list[dict[str, Any]]) -> dict[str, Any] | None:
        wanted = _identifier_aliases(site_ref)
        for site in sites:
            if _identifier_aliases(site.get("site_id"), site.get("alt_id"), *(site.get("identifiers") or [])) & wanted:
                return site
        return None

    def _filter_network(self, response: Network, sites: SiteResponse) -> Network:
        if not self._requested_sites or not response.items:
            return response

        allowed_site_ids = {item.id for item in sites.items}
        network_item = response.items[0]
        filtered_contains = [item for item in network_item.contains if item.id in allowed_site_ids]
        filtered_item = network_item.model_copy(update={"contains": filtered_contains})
        return Network(meta=response.meta, items=[filtered_item])

    def _filter_sites(self, response: SiteResponse) -> SiteResponse:
        if not self._requested_sites:
            return response

        wanted = _identifier_aliases(*self._requested_sites)
        filtered = [item for item in response.items if _identifier_aliases(item.id, *(item.identifier or [])) & wanted]
        return SiteResponse(meta=response.meta, items=filtered)

    def _filter_dataset_items(self, items: list, sites: SiteResponse) -> list:
        if not sites.items:
            return []
        allowed_site_ids: set[str] = set()
        for item in sites.items:
            allowed_site_ids.update(_identifier_aliases(item.id, *(item.identifier or [])))
        return [
            item
            for item in items
            if any(
                _identifier_aliases(originating_site.id) & allowed_site_ids
                for originating_site in (item.originating_site or [])
            )
        ]

    def _filter_observation_datasets(
        self, response: ObservationDatasetResponse, sites: SiteResponse
    ) -> ObservationDatasetResponse:
        return ObservationDatasetResponse(meta=response.meta, items=self._filter_dataset_items(response.items, sites))

    def _filter_timeseries_datasets(
        self, response: TimeSeriesDatasetResponse, sites: SiteResponse
    ) -> TimeSeriesDatasetResponse:
        return TimeSeriesDatasetResponse(meta=response.meta, items=self._filter_dataset_items(response.items, sites))

    def _filter_processing_configs(
        self,
        response: DataProcessingConfiguration,
        observation_datasets: ObservationDatasetResponse,
        timeseries_datasets: TimeSeriesDatasetResponse,
    ) -> DataProcessingConfiguration:
        all_items = list(observation_datasets.items) + list(timeseries_datasets.items)
        if not all_items:
            return DataProcessingConfiguration(meta=response.meta, items=[])

        allowed_dataset_ids: set[str] = set()
        for item in all_items:
            allowed_dataset_ids.update(_identifier_aliases(item.id))

        filtered = [
            item
            for item in response.items
            if any(_identifier_aliases(applies_to.id) & allowed_dataset_ids for applies_to in item.applies_to_dataset)
        ]
        return DataProcessingConfiguration(meta=response.meta, items=filtered)

    @staticmethod
    def _meta_dict() -> dict[str, Any]:
        return {
            "@id": "http://fdri.ceh.ac.uk/id/api-response/mock",
            "publisher": "UKCEH",
            "license": "https://creativecommons.org/licenses/by/4.0/",
            "licenseName": "CC BY 4.0",
            "comment": "Local simplified EddyPro metadata fixture",
            "version": "0.1.0",
            "hasFormat": ["application/json"],
        }

    @classmethod
    def _read_json(cls, filename: str) -> dict[str, Any]:
        path = cls.METADATA_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"Local EddyPro metadata fixture not found: {path}")
        return json.loads(path.read_text())
