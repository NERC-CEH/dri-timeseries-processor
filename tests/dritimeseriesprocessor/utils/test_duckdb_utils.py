import duckdb
import pytest

from dritimeseriesprocessor.utils.duckdb_utils import (
    get_duck_db_extensions,
    get_duck_db_secrets,
    get_duck_db_settings,
    parse_secret_string,
)


class TestGetDuckDbSettings:
    @pytest.mark.parametrize("key", ["Calendar", "TimeZone", "access_mode"])
    def test_get_settings_default(self, key: str) -> None:
        """Test that we get default settings. A basic selection of the settings taken from:
        https://duckdb.org/docs/stable/configuration/overview#global-configuration-options
        """
        conn = duckdb.connect()
        settings = get_duck_db_settings(conn)
        assert key in settings

    def test_settings_reflects_changes(self) -> None:
        conn = duckdb.connect()
        settings = get_duck_db_settings(conn)
        assert "force_download" not in settings

        conn.execute("SET force_download=true;")
        settings = get_duck_db_settings(conn)
        assert settings["force_download"] == "true"


class TestGetDuckDbExtensions:
    def test_get_extensions_default(self) -> None:
        """Test the status of core extensions. A basic selection taken from:
        https://duckdb.org/docs/stable/core_extensions/overview
        """
        conn = duckdb.connect()
        extensions = get_duck_db_extensions(conn)
        assert extensions["core_functions"]["loaded"]

    def test_get_extensions_after_install(self) -> None:
        """Test the status of extension after installation."""
        conn = duckdb.connect()
        extensions = get_duck_db_extensions(conn)
        assert not extensions["httpfs"]["loaded"]

        conn.execute("INSTALL httpfs; LOAD httpfs;")
        extensions = get_duck_db_extensions(conn)
        assert extensions["httpfs"]["loaded"]


class TestGetDuckDbSecrets:
    def test_get_duck_db_secrets_default(self) -> None:
        """Test default is for no secrets."""
        conn = duckdb.connect()
        secrets = get_duck_db_secrets(conn)
        assert secrets == {}

    def test_get_duck_db_secrets_after_adding(self) -> None:
        conn = duckdb.connect()
        conn.execute("""
            CREATE SECRET my_secret (
                TYPE S3,
                REGION 'eu-west-1'
            );
        """)
        secrets = get_duck_db_secrets(conn)
        assert secrets["my_secret"]["region"] == "eu-west-1"

    def test_get_duck_db_secrets_redacted(self) -> None:
        conn = duckdb.connect()
        conn.execute("""
            CREATE SECRET my_secret (
                TYPE S3,
                REGION 'eu-west-1',
                SECRET 'this should be redacted'
            );
        """)
        secrets = get_duck_db_secrets(conn)
        assert secrets["my_secret"]["region"] == "eu-west-1"
        assert secrets["my_secret"]["secret"] == "redacted"


class TestParseSecretString:
    @pytest.mark.parametrize(
        "secret_str, expected",
        [
            ("KEY=VALUE", {"KEY": "VALUE"}),
            ("A=1; B=2", {"A": "1", "B": "2"}),
            ("X=1; Y=2; Z=3;", {"X": "1", "Y": "2", "Z": "3"}),
            (" contains   =   spaces ;", {"contains": "spaces"}),
            ("equals=in=value;", {"equals": "in=value"}),
            ("no equals", {}),  # no valid pairs
        ],
    )
    def test_parse_secret_string(self, secret_str: str, expected: str) -> None:
        assert parse_secret_string(secret_str) == expected
