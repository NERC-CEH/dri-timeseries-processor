# import unittest
# from parameterized import parameterized

# from pydantic import ValidationError

# from metadata_manager.models.schemas.derivations import (
#     Measure,
#     Methodology,
#     DerivationMetadata
# )


# class TestMeasure(unittest.TestCase):
#     """Test Measure model"""
#     def test_extract_measure_info(self):
#         """Test extraction of measure id"""
#         test_data = {
#             "@id": "http://example.com/ref/common/measure/measure-id",
#             "hasUnit": {
#                 "prefLabel": ["mm/day"]
#             },
#             "aggregation": {
#                 "resolution": "P1D",
#                 "periodicity": "P1Y"
#             }
#         }
#         measure = Measure.model_validate(test_data)
#         self.assertEqual(measure.measure_id, "http://example.com/ref/common/measure/measure-id")

#     def test_extract_no_measure_info(self):
#         """Test validation fails if no measure id"""
#         test_data = {
#             "hasUnit": {
#                 "prefLabel": ["mm/day"]
#             },
#             "aggregation": {
#                 "resolution": "P1D",
#                 "periodicity": "P1Y"
#             }
#         }

#         with self.assertRaises(KeyError):
#             Measure.model_validate(test_data)


# class TestMethodology(unittest.TestCase):
#     """Test the Methodology model"""
#     def setUp(self):
#         self.test_data = {
#             "@id": "http://fdri.ceh.ac.uk/id/plan/derivation_id",
#             "uses":
#             [
#                 {
#                     "@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/use_1"
#                 },
#                 {
#                     "@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/use_2"
#                 }
#             ],
#             "configuration":
#             {
#                 "@id": "http://fdri.ceh.ac.uk/id/data-processing-configuration/pe_1day_processed",
#                 "type":
#                 {
#                     "@id": "http://fdri.ceh.ac.uk/ref/common/configuration-type/calculate"
#                 },
#                 "hasCurrentConfiguration":
#                 [
#                     {
#                         "@id": "http://fdri.ceh.ac.uk/id/configuration-item/pe_1day_processed-current",
#                         "method":
#                         {
#                             "@id": "http://fdri.ceh.ac.uk/ref/common/method/calculate-calc_daily_pe"
#                         }
#                     }
#                 ]
#             }
#         }

#     def test_extract_methodology_metadata(self):
#         """Test extraction of methodology metadata."""
#         methodology = Methodology.model_validate(self.test_data)
#         self.assertEqual(methodology.derivation_id, "http://fdri.ceh.ac.uk/id/plan/derivation_id")
#         self.assertEqual(methodology.uses,["http://fdri.ceh.ac.uk/ref/cosmos/time-series/use_1",
#                         "http://fdri.ceh.ac.uk/ref/cosmos/time-series/use_2"])
#         self.assertEqual(methodology.configuration_type, "http://fdri.ceh.ac.uk/ref/common/configuration-type/calculate")
#         self.assertEqual(methodology.method, "http://fdri.ceh.ac.uk/ref/common/method/calculate-calc_daily_pe")


#     @parameterized.expand([
#         ("test_missing_derivation_id", "@id"),
#         ("test_missing_configuration_type", "configuration")
#     ])
#     def test_missing_methodology_fields(self, _, field):
#         """Test validation fails if no metadata"""
#         invalid_data = self.test_data.copy()
#         del invalid_data[field]
#         with self.assertRaises(ValidationError):
#             Methodology.model_validate(invalid_data)


# class TestDerivationMetadata(unittest.TestCase):
#     """Test Derivation Metadata model"""
#     def setUp(self):
#         self.valid_data = {
#             "@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ts_def_id",
#             "prefLabel":
#             [
#                 "Potential evaporation"
#             ],
#             "measure":
#             {
#                 "@id": "http://fdri.ceh.ac.uk/ref/common/measure/measure_id"
#             },
#             "methodology":
#             {
#                 "@id": "http://fdri.ceh.ac.uk/id/plan/derivation_id",
#                 "uses":
#                 [
#                     {
#                         "@id": "http://fdri.ceh.ac.uk/ref/cosmos/time-series/use_1"
#                     }
#                 ],
#                 "configuration":
#                 {
#                     "@id": "http://fdri.ceh.ac.uk/id/data-processing-configuration/pe_1day_processed",
#                     "type":
#                     {
#                         "@id": "http://fdri.ceh.ac.uk/ref/common/configuration-type/calculate"
#                     },
#                     "hasCurrentConfiguration":
#                     [
#                         {
#                             "@id": "http://fdri.ceh.ac.uk/id/configuration-item/pe_1day_processed-current",
#                             "method":
#                             {
#                                 "@id": "http://fdri.ceh.ac.uk/ref/common/method/calculate-calc_daily_pe"
#                             }
#                         }
#                     ]
#                 }
#             }
#         }

#     def test_extract_derivation_metadata(self):
#         """Test extraction of derivation metadata."""
#         metadata = DerivationMetadata.model_validate(self.valid_data)

#         self.assertEqual(metadata.timeseries_def, "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ts_def_id")
#         self.assertEqual(metadata.measure.measure_id, "http://fdri.ceh.ac.uk/ref/common/measure/measure_id")
#         self.assertEqual(metadata.methodology.derivation_id, "http://fdri.ceh.ac.uk/id/plan/derivation_id")
#         self.assertEqual(metadata.methodology.uses, ["http://fdri.ceh.ac.uk/ref/cosmos/time-series/use_1"])
#         self.assertEqual(metadata.methodology.configuration_type, "http://fdri.ceh.ac.uk/ref/common/configuration-type/calculate")

#     def test_extract_derivation_metadata_no_methodology(self):
#         """Test extraction of derivation metadata if Methodology doesnt exist."""
#         no_methodology_data = self.valid_data.copy()
#         del no_methodology_data["methodology"]

#         metadata = DerivationMetadata.model_validate(no_methodology_data)

#         self.assertEqual(metadata.timeseries_def, "http://fdri.ceh.ac.uk/ref/cosmos/time-series/ts_def_id")
#         self.assertEqual(metadata.methodology, None)


#     @parameterized.expand([
#         ("test_missing_timeseries_def", "@id"),
#         ("test_missing_measure_id", "measure"),
#     ])
#     def test_missing_required_fields(self, _, field):
#         """Test validation fails when required fields are missing."""
#         invalid_data = self.valid_data.copy()
#         del invalid_data[field]
#         with self.assertRaises(KeyError):
#             DerivationMetadata.model_validate(invalid_data)
