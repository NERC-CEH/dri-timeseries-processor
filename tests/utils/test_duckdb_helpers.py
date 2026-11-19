import duckdb
import pytest

from utils.duckdb_helpers import get_duck_db_extensions, get_duck_db_secrets, get_duck_db_setting, parse_secret_string


class TestGetDuckDbSetting:
    @pytest.mark.parametrize("name", ["Calendar", "TimeZone", "access_mode"])
    def test_get_default_setting(self, name: str) -> None:
        """Tests that a default setting can be read from a new connection."""
        conn = duckdb.connect()
        assert get_duck_db_setting(conn, name) is not None

    def test_setting_reflects_changes(self) -> None:
        """Tests that a changed setting is returned with its new value."""
        conn = duckdb.connect()
        assert get_duck_db_setting(conn, "force_download") is False

        conn.execute("SET force_download=true;")
        assert get_duck_db_setting(conn, "force_download") is True

    def test_reads_s3_setting(self) -> None:
        """Tests that an S3 setting can be read, even though `duckdb_settings()` doesn't list it."""
        conn = duckdb.connect()
        conn.execute("SET s3_endpoint='some:url';")
        assert get_duck_db_setting(conn, "s3_endpoint") == "some:url"


class TestGetDuckDbExtensions:
    def test_get_extensions_default(self) -> None:
        """Tests that core extensions are loaded on a new connection."""
        conn = duckdb.connect()
        extensions = get_duck_db_extensions(conn)
        assert extensions["core_functions"]["loaded"]

    def test_get_extensions_after_install(self) -> None:
        """Tests that an extension shows as loaded after it is installed and loaded."""
        conn = duckdb.connect()
        extensions = get_duck_db_extensions(conn)
        assert not extensions["httpfs"]["loaded"]

        conn.execute("INSTALL httpfs; LOAD httpfs;")
        extensions = get_duck_db_extensions(conn)
        assert extensions["httpfs"]["loaded"]


class TestGetDuckDbSecrets:
    def test_get_duck_db_secrets_default(self) -> None:
        """Tests that a new connection has no secrets."""
        conn = duckdb.connect()
        secrets = get_duck_db_secrets(conn)
        assert secrets == {}

    def test_get_duck_db_secrets_after_adding(self) -> None:
        """Tests that a created secret is returned with its properties."""
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
        """Tests that a secret's private values are redacted."""
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
    def test_parse_secret_string(self, secret_str: str, expected: dict[str, str]) -> None:
        """Tests that a secret string is split into its named parts."""
        assert parse_secret_string(secret_str) == expected
