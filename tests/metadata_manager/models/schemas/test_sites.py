import unittest
from parameterized import parameterized

from pydantic import ValidationError

from metadata_manager.models.schemas.sites import Sites, SitesMetadata


class TestSites(unittest.TestCase):
    """Test the sites model"""
    def setUp(self):
        self.test_data = [
                {
                    "@id": "http://fdri.ceh.ac.uk/id/site/cosmos-rdmer",
                    "label":
                    [
                        "Redmere"
                    ]
                },
                {
                    "@id": "http://fdri.ceh.ac.uk/id/site/cosmos-hlacy",
                    "label":
                    [
                        "Holme Lacy"
                    ]
                }
            ]

    def test_extract_sites(self):
        """Test extraction of sites."""
        sites = Sites.model_validate(self.test_data)
        self.assertEqual(sites.site_list, ["http://fdri.ceh.ac.uk/id/site/cosmos-rdmer",
                                            "http://fdri.ceh.ac.uk/id/site/cosmos-hlacy"])

    @parameterized.expand([
        ("test_missing_site_id", None),
        ("test_invalid_site_id_type", 1234)
    ])
    def test_invalid_site_id_field(self, _, field):
        """Test validation fails if no metadata"""
        invalid_data = self.test_data.copy()
        invalid_data[0]["@id"] = field
        with self.assertRaises(ValidationError):
            Sites.model_validate(invalid_data)


class TestSitesMetadata(unittest.TestCase):
    """Test Sites Metadata model"""
    def setUp(self):
        self.test_data = {
            "@id": "http://fdri.ceh.ac.uk/id/network/cosmos",
            "contains":
            [
                {
                    "@id": "http://fdri.ceh.ac.uk/id/site/cosmos-rdmer",
                    "label":
                    [
                        "Redmere"
                    ]
                },
                {
                    "@id": "http://fdri.ceh.ac.uk/id/site/cosmos-hlacy",
                    "label":
                    [
                        "Holme Lacy"
                    ]
                }
            ],
            "@type":
            [
                {
                    "@id": "http://fdri.ceh.ac.uk/vocab/metadata/EnvironmentalMonitoringNetwork"
                }
            ],
            "label":
            [
                "COSMOS Network"
            ]
        }
    
    def test_extract_site_metadata_info(self):
        """Test extraction of site metadata."""

        metadata = SitesMetadata.model_validate(self.test_data)

        self.assertEqual(metadata.network_id, "http://fdri.ceh.ac.uk/id/network/cosmos")
        self.assertEqual(metadata.sites.site_list, ["http://fdri.ceh.ac.uk/id/site/cosmos-rdmer",
                                                    "http://fdri.ceh.ac.uk/id/site/cosmos-hlacy"])
        self.assertEqual(metadata.network_label, "COSMOS Network")
