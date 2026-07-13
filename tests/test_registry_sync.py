import unittest

from registry_sync import build_record


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


if __name__ == "__main__":
    unittest.main()
