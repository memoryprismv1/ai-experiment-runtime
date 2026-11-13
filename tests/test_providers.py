from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ai_experiment_runtime.providers import call_provider


class ProviderTests(unittest.TestCase):
    def test_openai_compatible_local_server_needs_no_api_key(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(length))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                body = json.dumps({
                    "choices": [{"message": {"content": "local model response"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11},
                }).encode()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = call_provider({
                "type": "openai-compatible",
                "model": "local-test-model",
                "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                "timeout_seconds": 5,
            }, "system", "task")
            self.assertEqual(result.text, "local model response")
            self.assertEqual(result.usage["total_tokens"], 11)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_mock_provider_is_deterministic(self) -> None:
        config = {"type": "mock", "model": "fixture-v1"}
        first = call_provider(config, "system", "task", "fixed output")
        second = call_provider(config, "system", "task", "fixed output")
        self.assertEqual(first.text, "fixed output")
        self.assertEqual(first.raw_response, second.raw_response)
        self.assertEqual(first.usage["mock"], True)

    def test_mock_provider_has_safe_default(self) -> None:
        result = call_provider({"type": "mock", "model": "fixture-v1"}, "system", "prompt")
        self.assertIn("MOCK RESPONSE", result.text)


if __name__ == "__main__":
    unittest.main()
