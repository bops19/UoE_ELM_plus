import importlib
import os
import unittest

os.environ.setdefault("OPENAI_API_KEY", "test-key")
app_module = importlib.import_module("app")


class ErrorContractTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self._original_api_key = app_module.app.config.get("API_KEY")

    def tearDown(self):
        app_module.app.config["API_KEY"] = self._original_api_key

    def _assert_error_contract(self, payload: dict):
        self.assertIsInstance(payload, dict)
        self.assertIn("error", payload)
        self.assertIsInstance(payload["error"], dict)
        self.assertIn("code", payload["error"])
        self.assertIn("message", payload["error"])
        self.assertIn("requestId", payload["error"])
        self.assertIn("errorCode", payload)
        self.assertIn("message", payload)
        self.assertIn("requestId", payload)
        self.assertEqual(payload["errorCode"], payload["error"]["code"])
        self.assertEqual(payload["message"], payload["error"]["message"])
        self.assertEqual(payload["requestId"], payload["error"]["requestId"])

    def test_chat_validation_error_uses_structured_contract(self):
        response = self.client.post("/chat", json={})
        self.assertEqual(400, response.status_code)
        payload = response.get_json()
        self._assert_error_contract(payload)

    def test_missing_session_error_uses_structured_contract(self):
        response = self.client.get("/sessions/non-existent-session-id")
        self.assertEqual(404, response.status_code)
        payload = response.get_json()
        self._assert_error_contract(payload)

    def test_api_key_guard_blocks_without_header_when_enabled(self):
        app_module.app.config["API_KEY"] = "test-secret"
        response = self.client.get("/sessions")
        self.assertEqual(401, response.status_code)
        payload = response.get_json()
        self._assert_error_contract(payload)
        self.assertEqual("UNAUTHORIZED", payload["error"]["code"])

    def test_api_key_guard_allows_matching_header(self):
        app_module.app.config["API_KEY"] = "test-secret"
        response = self.client.get("/sessions", headers={"X-API-Key": "test-secret"})
        self.assertEqual(200, response.status_code)


if __name__ == "__main__":
    unittest.main()
