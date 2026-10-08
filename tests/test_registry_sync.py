import unittest
from unittest.mock import patch

from registry_sync import build_record, search_registry


class RegistrySyncTest(unittest.TestCase):
    def test_build_record_preserves_registry_version_and_repository(self):
        entry = {
            "server": {
                "name": "io.github.example/robot-mcp",
                "title": "Robot MCP",
                "description": "Controls a robot",
                "version": "1.2.3",
                "repository": {"url": "https://github.com/example/robot-mcp"},
                "packages": [{"registryType": "pypi", "identifier": "robot-mcp"}],
            },
            "_meta": {
                "io.modelcontextprotocol.registry/official": {
                    "isLatest": True,
                    "updatedAt": "2026-07-01T00:00:00Z",
                }
            },
            "_matchedKeyword": "robot",
        }
        source = {
            "endpoint": "https://registry.example/v0.1/servers",
            "source_url": "https://registry.example",
        }
        record = build_record("official", source, entry)
        self.assertEqual(record["version"], "1.2.3")
        self.assertEqual(record["url"], "https://github.com/example/robot-mcp")
        self.assertEqual(record["decision"], "review")

    def test_failed_later_page_preserves_completed_discoveries(self):
        entry = {"server": {"name": "example/robot"}, "_meta": {
            "io.modelcontextprotocol.registry/official": {"isLatest": True},
        }}
        errors = []
        with patch("registry_sync.fetch_json", side_effect=[
            {"servers": [entry], "metadata": {"nextCursor": "page-two"}},
            TimeoutError("read timeout"),
        ]):
            results = search_registry("https://registry.example", ["robot"], errors=errors)
        self.assertIn("example/robot", results)
        self.assertEqual(errors[0]["cursor"], "page-two")

    def test_pagination_cap_is_explicit_in_report(self):
        errors = []
        cursors = {}
        with patch("registry_sync.fetch_json", return_value={
            "servers": [], "metadata": {"nextCursor": "more"},
        }):
            search_registry("https://registry.example", ["robot"], max_pages=1,
                            errors=errors, cursors=cursors)
        self.assertEqual(errors, [])
        self.assertEqual(cursors, {"robot": "more"})
        with patch("registry_sync.fetch_json", return_value={"servers": []}) as fetch:
            search_registry("https://registry.example", ["robot"], cursors=cursors)
        self.assertIn("cursor=more", fetch.call_args.args[0])
        self.assertEqual(cursors, {})


if __name__ == "__main__":
    unittest.main()
