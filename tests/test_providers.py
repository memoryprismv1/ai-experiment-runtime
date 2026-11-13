from __future__ import annotations

import unittest

from ai_experiment_runtime.providers import call_provider


class ProviderTests(unittest.TestCase):
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
