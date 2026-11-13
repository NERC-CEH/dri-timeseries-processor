from types import SimpleNamespace
from unittest.mock import MagicMock

import duckdb
import pytest

from dritimeseriesprocessor.io_backend.duckdb_connection import (
    AwsDuckDBConnectionFactory,
    LocalStackDuckDBConnectionFactory,
    MinimalDuckDBConnectionFactory,
    create_duckdb_factory,
)
from dritimeseriesprocessor.utils.enums import Environment
from utils.duckdb_helpers import get_duck_db_extensions, get_duck_db_secrets, get_duck_db_setting


class TestDuckDBConnectionFactory:
    def test_base_creates_connection(self) -> None:
        """Tests that the base setup turns on `force_download` and loads the httpfs extension."""
        factory = MinimalDuckDBConnectionFactory()
        conn = factory.create()
        assert isinstance(conn, duckdb.DuckDBPyConnection)

        assert get_duck_db_setting(conn, "force_download") is True

        extensions = get_duck_db_extensions(conn)
        assert extensions["httpfs"]["installed"]
        assert extensions["httpfs"]["loaded"]

    def test_local_factory_configures_localstack_sql(self) -> None:
        """Tests that the LocalStack factory sets the S3 endpoint and credentials on the connection."""
        factory = LocalStackDuckDBConnectionFactory(
            endpoint_url="http://some:url",
            aws_access_key="ABC",
            aws_secret_key="XYZ",
        )
        conn = factory.create()

        assert isinstance(conn, duckdb.DuckDBPyConnection)

        assert get_duck_db_setting(conn, "s3_endpoint") == "some:url"
        assert get_duck_db_setting(conn, "s3_url_style") == "path"
        assert get_duck_db_setting(conn, "s3_use_ssl") is False
        assert get_duck_db_setting(conn, "s3_access_key_id") == "ABC"
        assert get_duck_db_setting(conn, "s3_secret_access_key") == "XYZ"

        # No secrets should have been set
        secrets = get_duck_db_secrets(conn)
        assert secrets == {}

    def test_aws_factory_uses_boto_credentials(self) -> None:
        """Tests that the AWS factory creates an S3 secret from the boto3 session's credentials."""
        # Fake boto session + credentials
        fake_creds = MagicMock()
        fake_creds.access_key = "AAA"
        fake_creds.secret_key = "BBB"
        fake_creds.token = "CCC"
        fake_session = MagicMock()
        fake_session.region_name = "eu-west-2"
        fake_session.get_credentials.return_value.get_frozen_credentials.return_value = fake_creds

        factory = AwsDuckDBConnectionFactory(fake_session)
        conn = factory.create()
        assert isinstance(conn, duckdb.DuckDBPyConnection)

        secrets = get_duck_db_secrets(conn)
        assert secrets["aws_secret"]["type"] == "s3"
        assert secrets["aws_secret"]["key_id"] == "AAA"
        assert secrets["aws_secret"]["region"] == "eu-west-2"
        assert secrets["aws_secret"]["secret"] == "redacted"
        assert secrets["aws_secret"]["session_token"] == "redacted"


class TestCreateDuckdbFactory:
    @staticmethod
    def mock_app_config(mock_config: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "dritimeseriesprocessor.io_backend.duckdb_connection.app_config", MagicMock(return_value=mock_config)
        )

    def test_create_duckdb_factory_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_config = SimpleNamespace(
            environment=Environment.LOCAL,
            endpoint_url="http://ls",
            AWS_ACCESS_KEY_ID="111",
            AWS_SECRET_ACCESS_KEY="222",
        )
        self.mock_app_config(mock_config, monkeypatch)

        factory = create_duckdb_factory()
        assert isinstance(factory, LocalStackDuckDBConnectionFactory)

    @pytest.mark.parametrize("env", ["staging", "production"])
    def test_create_duckdb_factory_live(self, env: str, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_config = SimpleNamespace(
            environment=Environment(env),
        )
        self.mock_app_config(mock_config, monkeypatch)

        factory = create_duckdb_factory()
        assert isinstance(factory, AwsDuckDBConnectionFactory)

    def test_create_duckdb_factory_fake(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_config = SimpleNamespace(
            environment=Environment.STAGING_FAKE,
        )
        self.mock_app_config(mock_config, monkeypatch)

        factory = create_duckdb_factory()
        assert isinstance(factory, MinimalDuckDBConnectionFactory)
