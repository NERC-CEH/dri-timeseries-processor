from typing import Any, Dict

import pytest
from pydantic import ValidationError

from metadata_manager.models.schemas.sites import Sites, SitesMetadata


class TestSites:
    """Test the sites model"""

    @property
    def test_data(self) -> Dict[str, Any]:
        test_data = [
            {"@id": "http://fdri.ceh.ac.uk/id/site/cosmos-rdmer", "label": ["Redmere"]},
            {"@id": "http://fdri.ceh.ac.uk/id/site/cosmos-hlacy", "label": ["Holme Lacy"]},
        ]
        return test_data

    def test_extract_sites(self) -> None:
        """Test extraction of sites."""
        sites = Sites.model_validate(self.test_data)
        assert sites.site_list == [
            "http://fdri.ceh.ac.uk/id/site/cosmos-rdmer",
            "http://fdri.ceh.ac.uk/id/site/cosmos-hlacy",
        ]

    @pytest.mark.parametrize("field", [(None), (1234)], ids=["test_missing_site_id", "test_invalid_site_id_type"])
    def test_invalid_site_id_field(self, field: Any | None) -> None:
        """Test validation fails if no metadata"""
        invalid_data = self.test_data.copy()
        invalid_data[0]["@id"] = field

        with pytest.raises(ValidationError):
            Sites.model_validate(invalid_data)


class TestSitesMetadata:
    """Test Sites Metadata model"""

    @property
    def test_data(self) -> Dict[str, Any]:
        test_data = {
            "@id": "http://fdri.ceh.ac.uk/id/network/cosmos",
            "contains": [
                {"@id": "http://fdri.ceh.ac.uk/id/site/cosmos-rdmer", "label": ["Redmere"]},
                {"@id": "http://fdri.ceh.ac.uk/id/site/cosmos-hlacy", "label": ["Holme Lacy"]},
            ],
            "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/EnvironmentalMonitoringNetwork"}],
            "label": ["COSMOS Network"],
        }
        return test_data

    def test_extract_site_metadata_info(self) -> None:
        """Test extraction of site metadata."""

        metadata = SitesMetadata.model_validate(self.test_data.copy())

        assert metadata.network_id == "http://fdri.ceh.ac.uk/id/network/cosmos"
        assert metadata.sites.site_list == [
            "http://fdri.ceh.ac.uk/id/site/cosmos-rdmer",
            "http://fdri.ceh.ac.uk/id/site/cosmos-hlacy",
        ]
        assert metadata.network_label == "COSMOS Network"

    @pytest.mark.parametrize(
        "field,error",
        [
            ("@id", ValidationError),
            ("label", ValidationError),
            ("contains", KeyError),
        ],
        ids=["test missing network id", "test missing label", "test missing contains"],
    )
    def test_missing_required_fields(self, field: str, error: str) -> None:
        """Test validation fails when required fields are missing."""
        invalid_data = self.test_data.copy()
        del invalid_data[field]
        with pytest.raises(error):
            SitesMetadata.model_validate(invalid_data)
