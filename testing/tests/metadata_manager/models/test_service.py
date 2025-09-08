import datetime
from unittest import mock

from metadata_manager.api_manager import MetadataAPIManager
from metadata_manager.models.schemas.data_processing_configurations import DataProcessingConfiguration
from metadata_manager.models.service import update_correction_configs_with_site_attributes
from testing.utils.base_test_helper import BaseTestHelper
from testing.utils.mock_metadata_api import MockMetadataAPI


@mock.patch.object(MetadataAPIManager, "_make_api_call")
class TestUpdateCorrectionConfigsWithSiteAttributes(BaseTestHelper):
    def setUp(self) -> None:
        super().setUp()
        self.host_url = "test_url.com"
        self.api = MetadataAPIManager(host=self.host_url, network="cosmos")

    def test_update_correction_configs_with_site_attribute(self, mock_metadata_api: mock.MagicMock) -> None:
        response_data = {
            "meta": {},
            "items": [{"@id": "http://fdri.ceh.ac.uk/id/site/cosmos-alic1", "altitude": 123.45}],
        }
        mock_api_data = {"https://dri-metadata-api.staging.eds.ceh.ac.uk/id/site/cosmos-holln": response_data}
        mock_metadata_api.side_effect = MockMetadataAPI(api_data=mock_api_data)

        corr_config = DataProcessingConfiguration.model_validate(
            {
                "@id": "http://fdri.ceh.ac.uk/id/data-processing-configuration/ii0qv3mdrsrtl84rug79ornp0ihl28sg",
                "appliesToTimeSeries": [
                    {
                        "@id": "http://fdri.ceh.ac.uk/id/dataset/cosmos-holln-pa_30min_raw",
                        "originatingSite": {"@id": "http://fdri.ceh.ac.uk/id/site/cosmos-holln"},
                    }
                ],
                "hasCurrentConfiguration": [
                    {
                        "@id": "http://fdri.ceh.ac.uk/id/configuration-item/hc8bbgabvdq71nb5sic9dt75lnragd4g",
                        "argument": [
                            {
                                "@id": "http://fdri.ceh.ac.uk/id/argument/sliccqhahus0t1j9053ejd3eqg9id0lj",
                                "hasValue": {
                                    "@id": "http://fdri.ceh.ac.uk/id/argument/sliccqhahus0t1j9053ejd3eqg9id0lj#value",
                                    "value": "ALTITUDE",
                                },
                                "parameter": {"@id": "http://fdri.ceh.ac.uk/ref/common/parameter/site_attribute"},
                                "@type": [{"@id": "http://fdri.ceh.ac.uk/vocab/metadata/ConfigurationArgument"}],
                            },
                        ],
                        "method": {"@id": "http://fdri.ceh.ac.uk/ref/common/method/pa_corr"},
                        "observationInterval": {
                            "@id": "http://fdri.ceh.ac.uk/id/observation-interval/2022-02-01-00:30:00-2022-03-01-00:00:00",
                            "@type": [{"@id": "http://purl.org/dc/terms/PeriodOfTime"}],
                            "endDate": "2022-03-01T00:00:00",
                            "startDate": "2022-02-01T00:30:00",
                        },
                    }
                ],
            },
        )

        expected_updated_config = {
            "name": "pa_corr",
            "interval": (datetime.datetime(1800, 1, 1, 0, 0), None),
            "observation_interval": (datetime.datetime(2022, 2, 1, 0, 30), datetime.datetime(2022, 3, 1, 0, 0)),
            "parameters": {"altitude": 123.45},
        }

        updated_configs = update_correction_configs_with_site_attributes([corr_config])
        assert updated_configs[0].configs[0].dict() == expected_updated_config
