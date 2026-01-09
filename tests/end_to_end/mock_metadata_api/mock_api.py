import json
import socket
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Iterator

import pytest
from tests.utils.fixture_helpers import TEST_DATA_MOCK_METADATA
from tests.utils.metadata_helpers import stable_file_key


class MockMetadataApi(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle(self) -> None:
        file_key = stable_file_key(self.path)
        file_path = Path(TEST_DATA_MOCK_METADATA / f"{file_key}.json")

        if not file_path.exists():
            self._send_json(
                500,
                {
                    "error": "No fixture for request",
                    "path": self.path,
                    "expected_fixture": str(file_path),
                },
            )
        else:
            self._send_json(200, json.loads(file_path.read_text()))

    def do_GET(self) -> None:
        self._handle()


@pytest.fixture
def metadata_api_url() -> Iterator[str]:
    """Start a local mock metadata API server and yield its base URL.

    Yields:
        The base URL of the running mock metadata API.
    """
    with mock_metadata_api() as url:
        yield url


@contextmanager
def mock_metadata_api() -> Iterator[str]:
    """Start a local mock metadata API server and yield its base URL."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    server = HTTPServer(("127.0.0.1", port), MockMetadataApi)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
