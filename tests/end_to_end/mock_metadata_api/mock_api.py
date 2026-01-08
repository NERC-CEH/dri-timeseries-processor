import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path

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
