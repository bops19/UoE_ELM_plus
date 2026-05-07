import importlib
import os
import unittest

os.environ.setdefault("OPENAI_API_KEY", "test-key")
app_module = importlib.import_module("app")


class BlueprintRoutesSmokeTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_blueprint_route_rules_registered(self):
        rules = {(rule.rule, tuple(sorted(rule.methods))) for rule in app_module.app.url_map.iter_rules()}

        self.assertIn(("/sessions", ("GET", "HEAD", "OPTIONS")), rules)
        self.assertIn(("/chat", ("OPTIONS", "POST")), rules)
        self.assertIn(("/sessions/<session_id>/voice/bootstrap", ("OPTIONS", "POST")), rules)
        self.assertIn(("/computer-runs/start", ("OPTIONS", "POST")), rules)
        self.assertIn(("/embed-index", ("OPTIONS", "POST")), rules)
        self.assertIn(("/prompt-presets", ("GET", "HEAD", "OPTIONS")), rules)
        self.assertIn(("/settings", ("OPTIONS", "POST")), rules)
        self.assertIn(("/model-catalog", ("GET", "HEAD", "OPTIONS")), rules)
        self.assertIn(("/vm/usage", ("GET", "HEAD", "OPTIONS")), rules)
        self.assertIn(("/vm/catalog", ("GET", "HEAD", "OPTIONS")), rules)
        self.assertIn(("/vm/session/<session_id>", ("GET", "HEAD", "OPTIONS")), rules)
        self.assertIn(("/app", ("GET", "HEAD", "OPTIONS")), rules)
        self.assertIn(("/app/", ("GET", "HEAD", "OPTIONS")), rules)
        self.assertIn(("/app/<path:subpath>", ("GET", "HEAD", "OPTIONS")), rules)
        self.assertNotIn(("/legacy", ("GET", "HEAD", "OPTIONS")), rules)
        self.assertFalse(any(rule[0] == "/legacy-static/<path:subpath>" for rule in rules))

    def test_representative_routes_respond(self):
        sessions_resp = self.client.get("/sessions")
        self.assertEqual(200, sessions_resp.status_code)

        presets_resp = self.client.get("/prompt-presets")
        self.assertEqual(200, presets_resp.status_code)

        chat_resp = self.client.post("/chat", json={})
        self.assertEqual(400, chat_resp.status_code)

        vm_catalog_resp = self.client.get("/vm/catalog")
        self.assertEqual(200, vm_catalog_resp.status_code)

        vm_usage_resp = self.client.get("/vm/usage?sessionId=test")
        self.assertEqual(200, vm_usage_resp.status_code)

        angular_shell_resp = self.client.get("/app")
        self.assertIn(angular_shell_resp.status_code, {200, 503})
        _ = angular_shell_resp.get_data()

        angular_shell_slash_resp = self.client.get("/app/")
        self.assertIn(angular_shell_slash_resp.status_code, {200, 503})
        _ = angular_shell_slash_resp.get_data()

        root_resp = self.client.get("/", follow_redirects=False)
        self.assertEqual(302, root_resp.status_code)
        self.assertIn("/app", root_resp.headers.get("Location", ""))

        legacy_shell_resp = self.client.get("/legacy")
        self.assertEqual(404, legacy_shell_resp.status_code)

        legacy_asset_resp = self.client.get("/legacy-static/images/logo.png")
        self.assertEqual(404, legacy_asset_resp.status_code)

    def test_image_routes_still_registered_on_app(self):
        rules = {(rule.rule, tuple(sorted(rule.methods))) for rule in app_module.app.url_map.iter_rules()}
        self.assertIn(("/image", ("OPTIONS", "POST")), rules)
        self.assertIn(("/image/edit", ("OPTIONS", "POST")), rules)
        self.assertIn(("/image-projects", ("GET", "HEAD", "OPTIONS")), rules)


if __name__ == "__main__":
    unittest.main()
