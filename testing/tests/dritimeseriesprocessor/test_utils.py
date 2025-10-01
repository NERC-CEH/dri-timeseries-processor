import re
from datetime import date, datetime
from typing import Any, Dict

import polars as pl
import polars.testing
import pytest

from dritimeseriesprocessor import utils
from metadata_manager.models.common import SERVICE_BASE_URI


class TestValidateISO8601Duration:
    def test_valid_duration_full_format(self) -> None:
        """Test a valid ISO 8601 duration in full format."""
        duration = "P1Y2M3DT4H5M6S"
        assert utils.validate_iso8601_duration(duration)

    def test_valid_duration_days_only(self) -> None:
        """Test a valid ISO 8601 duration with days only."""
        duration = "P3D"
        assert utils.validate_iso8601_duration(duration)

    def test_valid_duration_hours_only(self) -> None:
        """Test a valid ISO 8601 duration with hours only."""
        duration = "PT4H"
        assert utils.validate_iso8601_duration(duration)

    def test_valid_duration_combination(self) -> None:
        """Test a valid ISO 8601 duration with a combination of elements."""
        duration = "P2W"
        assert utils.validate_iso8601_duration(duration)

    def test_invalid_duration_missing_p(self) -> None:
        """Test an invalid ISO 8601 duration missing the 'P' character."""
        duration = "1Y2M3DT4H5M6S"
        assert not utils.validate_iso8601_duration(duration)

    def test_invalid_duration_wrong_format(self) -> None:
        """Test an invalid ISO 8601 duration with a wrong format."""
        duration = "P1Y2M3D4H5M6S"
        assert not utils.validate_iso8601_duration(duration)

    def test_invalid_duration_non_iso_string(self) -> None:
        """Test an invalid ISO 8601 duration with a non-ISO string."""
        duration = "This is not a duration"
        assert not utils.validate_iso8601_duration(duration)

    def test_empty_string(self) -> None:
        """Test an invalid ISO 8601 duration with an empty string."""
        duration = ""
        assert not utils.validate_iso8601_duration(duration)


class TestRemoveProtocolFromUrl:
    def test_https_url(self) -> None:
        """Test removing protocol from an HTTPS URL."""
        url = "https://www.example.com"
        expected = "www.example.com"
        result = utils.remove_protocol_from_url(url)
        assert result == expected

    def test_http_url(self) -> None:
        """Test removing protocol from an HTTP URL."""
        url = "http://www.example.com"
        expected = "www.example.com"
        result = utils.remove_protocol_from_url(url)
        assert result == expected

    def test_url_with_path(self) -> None:
        """Test removing protocol from a URL with a path."""
        url = "https://www.example.com/path/to/resource"
        expected = "www.example.com/path/to/resource"
        result = utils.remove_protocol_from_url(url)
        assert result == expected

    def test_url_with_port(self) -> None:
        """Test removing protocol from a URL with a port."""
        url = "https://www.example.com:8080"
        expected = "www.example.com:8080"
        result = utils.remove_protocol_from_url(url)
        assert result == expected

    def test_url_without_protocol(self) -> None:
        """Test a URL that already has no protocol."""
        url = "www.example.com"
        expected = "www.example.com"
        result = utils.remove_protocol_from_url(url)
        assert result == expected


class TestSterilizeDates:
    def test_start_date_only(self) -> None:
        """Test with only start_date provided as date that datetimes of start and end of that date are returned"""
        start = date(2023, 8, 1)
        expected_start = datetime.combine(start, datetime.min.time())
        expected_end = datetime.combine(start, datetime.max.time())
        result = utils.sterilize_dates(start)
        assert result == (expected_start, expected_end)

    def test_start_date_and_end_date_as_dates(self) -> None:
        """Test with both start_date and end_date provided as dates that datetimes are returned"""
        start = date(2023, 8, 1)
        end = date(2023, 8, 10)
        expected_start = datetime.combine(start, datetime.min.time())
        expected_end = datetime.combine(end, datetime.max.time())
        result = utils.sterilize_dates(start, end)
        assert result == (expected_start, expected_end)

    def test_start_date_after_end_date_error(self) -> None:
        """Test with start_date after end_date, should raise UserWarning."""
        start = date(2023, 8, 10)
        end = date(2023, 8, 1)
        with pytest.raises(UserWarning):
            utils.sterilize_dates(start, end)

    def test_start_date_equals_end_date(self) -> None:
        """Test with start_date equal to end_date that datetimes of start and end of that date are returned."""
        start = date(2023, 8, 1)
        end = date(2023, 8, 1)
        expected_start = datetime.combine(start, datetime.min.time())
        expected_end = datetime.combine(end, datetime.max.time())
        result = utils.sterilize_dates(start, end)
        assert result == (expected_start, expected_end)

    def test_datetime_input(self) -> None:
        """Test with datetime inputs for both start_date and end_date."""
        start = datetime(2023, 8, 1, 12, 0)
        end = datetime(2023, 8, 10, 18, 0)
        result = utils.sterilize_dates(start, end)
        assert result == (start, end)

    def test_mixed_date_and_datetime(self) -> None:
        """Test with start_date as date and end_date as datetime."""
        start = date(2023, 8, 1)
        end = datetime(2023, 8, 10, 18, 0)
        expected_start = datetime.combine(start, datetime.min.time())
        result = utils.sterilize_dates(expected_start, end)
        assert result == (expected_start, end)


class TestMissingExpr:
    def test_missing_expr(self) -> None:
        """Test the expression for detecting missing values."""
        expr = utils.missing_expr("value")
        df = pl.DataFrame({"value": [10, None, 30, float("nan"), 50]}, strict=False)
        result = df.with_columns(expr.alias("is_missing"))
        assert result["is_missing"].to_list() == [False, True, False, True, False]


class TestNotMissingExpr:
    def test_not_missing_expr(self) -> None:
        """Test the expression for detecting non-missing values."""
        expr = utils.not_missing_expr("value")
        df = pl.DataFrame({"value": [10, None, 30, float("nan"), 50]}, strict=False)
        result = df.with_columns(expr.alias("is_not_missing"))
        assert result["is_not_missing"].to_list() == [True, False, True, False, True]


class DummyDepTS:
    def __init__(self, column_name: str) -> None:
        self.metadata = {"column_name": column_name}


class DummyConfigItem:
    def __init__(self, parameters: Dict[str, str]) -> None:
        self.parameters = parameters


class TestExtractDepTs:
    @property
    def dep_ts1(self) -> DummyDepTS:
        return DummyDepTS("DEP1")

    @property
    def dep_ts2(self) -> DummyDepTS:
        return DummyDepTS("DEP2")

    @property
    def ts_ids(self) -> Dict[str, Any]:
        ts_ids = {
            f"{SERVICE_BASE_URI}/id/dataset/dep1": {"data": DummyDepTS("DEP1")},
            f"{SERVICE_BASE_URI}/id/dataset/dep2": {"data": DummyDepTS("DEP2")},
        }
        return ts_ids

    def test_single_dep_ts_as_string(self) -> None:
        """Test with a single dependency time series ID as a string."""
        config = DummyConfigItem(parameters={"dep_ts": "DEP1"})

        result = utils.extract_dep_ts(config, self.ts_ids)

        assert "dep_ts" not in result.parameters

        assert isinstance(result.parameters["dep1"], DummyDepTS)
        assert result.parameters["dep1"].metadata["column_name"] == "DEP1"

    def test_multiple_dep_ts_as_list(self) -> None:
        """Test with multiple dependency time series IDs as a list."""
        config = DummyConfigItem(parameters={"dep_ts": ["DEP1", "DEP2"]})

        result = utils.extract_dep_ts(config, self.ts_ids)

        assert "dep_ts" not in result.parameters

        for key, expected_column_name in [("dep1", "DEP1"), ("dep2", "DEP2")]:
            assert isinstance(result.parameters[key], DummyDepTS)
            assert result.parameters[key].metadata["column_name"] == expected_column_name

    def test_dep_ts_not_found_raises(self) -> None:
        """Test that a ValueError is raised if a dependency time series ID is not found."""
        config = DummyConfigItem(parameters={"dep_ts": "NOTFOUND"})

        with pytest.raises(ValueError, match="Dependency time series ID NOTFOUND not found"):
            utils.extract_dep_ts(config, self.ts_ids)

    def test_no_dep_ts_key(self) -> None:
        """Test that the config is returned unchanged if there is no 'dep_ts' key."""
        config = DummyConfigItem(parameters={"other_param": 123})
        result = utils.extract_dep_ts(config, self.ts_ids)

        assert result.parameters == {"other_param": 123}

    def test_dep_ts_case_insensitive(self) -> None:
        """Test that dependency time series IDs are handled case-insensitively."""
        config = DummyConfigItem(parameters={"dep_ts": "dep1"})
        result = utils.extract_dep_ts(config, self.ts_ids)

        assert isinstance(result.parameters["dep1"], DummyDepTS)
        assert result.parameters["dep1"].metadata["column_name"] == "DEP1"


class TestSplitDataForProcessing:
    """Test the split_data_for_processing function."""

    def test_split_data_for_processing(self) -> None:
        """Test that df is split correctly."""

        data = {
            "time": [
                datetime(2024, 1, 1, 1, 10, 0),
                datetime(2024, 1, 1, 1, 10, 0),
                datetime(2024, 1, 2, 1, 10, 0),
                datetime(2024, 1, 2, 1, 10, 0),
                datetime(2024, 1, 3, 1, 10, 0),
                datetime(2024, 1, 3, 1, 10, 0),
            ],
            "SITE_ID": ["site1", "site1", "site1", "site2", "site3", "site3"],
            "value": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
        }
        schema = {"time": pl.Datetime, "SITE_ID": pl.String, "value": pl.Float64}

        df = pl.DataFrame(data, schema)
        metadata = {"test": "test_metadata"}

        result = utils.split_data_for_processing(df, metadata)

        # Should be 3 dataframes
        assert len(result) == 3

        for site, data, metadata in result:
            expected = df.filter((pl.col("SITE_ID") == site))
            polars.testing.assert_frame_equal(data, expected)

            assert metadata == {"test": "test_metadata"}


class TestRemoveSitesNotInStore:
    """Test the remove_sites_not_in_store function."""

    def test_all_sites_in_store(self) -> None:
        sites = ["A", "B"]
        metadata_sites = ["A", "B", "C"]

        result = utils.remove_sites_not_in_store(sites, metadata_sites)

        assert sorted(result) == sorted(["A", "B"])

    def test_one_site_not_in_store(self) -> None:
        sites = ["A", "B"]
        metadata_sites = ["A"]

        expected_error = "The following sites ['B'] are not in the metadata store. Remove from '--sites' argument."
        with pytest.raises(ValueError, match=re.escape(expected_error)):
            utils.remove_sites_not_in_store(sites, metadata_sites)


class TestMapDefToId:
    """Test the map_def_to_id function."""

    @property
    def test_ts_ids(self) -> Dict[str, Dict[str, str]]:
        test_ts_ids = {
            "alic1-precip_30min_raw": {
                "ts_def": "precip_30min_raw",
                "processing_level": "raw",
                "sourceSite": "ALIC1",
            },
            "alic1-ta_30min_raw": {
                "ts_def": "ta_30min_raw",
                "processing_level": "raw",
                "sourceSite": "ALIC1",
            },
        }
        return test_ts_ids

    def test_map_def_to_id(self) -> None:
        """Test that the correct ts_id is returned for a given ts_def and site_id."""
        result = utils.map_def_to_id("ta_30min_raw", "ALIC1", self.test_ts_ids)
        assert result == "alic1-ta_30min_raw"

    def test_no_matching_ts_def(self) -> None:
        """Test that a ValueError is raised when no matching ts_def is found."""
        with pytest.raises(ValueError):
            utils.map_def_to_id("non_existent_def", "ALIC1", self.test_ts_ids)
