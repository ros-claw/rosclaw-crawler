import unittest
from http.client import RemoteDisconnected
from unittest.mock import MagicMock, patch

from github_discovery import GitHubClient, discover, skill_record, skill_results_from_repository


SKILL_TEMPLATE = """---
name: {name}
description: Operate and troubleshoot a RealSense depth camera for robot perception.
---
# {name}
## Workflow
Use scripts/check.py to verify the RealSense camera before robot operation.
"""


class FakeGitHubClient:
    def __init__(self, repo, paths):
        self.repo = repo
        self.paths = paths
        self.blobs = {
            f"https://api.github.test/blob/{index}": SKILL_TEMPLATE.format(
                name=path.split("/")[-2]
            )
            for index, path in enumerate(paths)
        }

    def search(self, kind, query, per_page):
        return [self.repo] if kind == "repositories" else []

    def get(self, path, params=None):
        if path == f"/repos/{self.repo['full_name']}":
            return self.repo
        if path == f"/repos/{self.repo['full_name']}/git/trees/main":
            return {
                "tree": [
                    {
                        "path": skill_path,
                        "type": "blob",
                        "sha": f"sha-{index}",
                        "url": f"https://api.github.test/blob/{index}",
                    }
                    for index, skill_path in enumerate(self.paths)
                ] + [{"path": "README.md", "type": "blob", "url": "ignored"}]
            }
        raise AssertionError(f"unexpected get: {path} {params}")

    def content(self, url):
        return self.blobs[url]


class GitHubSkillRepositoryDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.repo = {
            "full_name": "example/realsense-skills",
            "name": "realsense-skills",
            "html_url": "https://github.com/example/realsense-skills",
            "default_branch": "main",
            "description": "Agentic skills for RealSense robot perception",
            "owner": {"login": "example"},
        }
        self.paths = [
            "skills/device-setup/SKILL.md",
            "skills/troubleshoot/SKILL.md",
        ]
        self.client = FakeGitHubClient(self.repo, self.paths)

    def test_tree_enumeration_does_not_depend_on_code_search(self):
        results = skill_results_from_repository(self.client, self.repo)
        self.assertEqual([result["path"] for result in results], self.paths)
        self.assertTrue(all(result["repository"] is self.repo for result in results))

    def test_repository_search_stages_each_skill_individually(self):
        config = {
            "taxonomy": "missing-taxonomy.yaml",
            "skill_repositories": ["skills RealSense in:name,description,readme"],
            "max_results_per_query": 10,
            "max_skill_repositories_per_run": 5,
            "max_skills_per_repository": 10,
        }
        records, next_state = discover(config, self.client)
        skills = [record for item_type, record in records if item_type == "skill"]
        self.assertIsNone(next_state)
        self.assertEqual(len(skills), 2)
        self.assertEqual(
            {record["full_name"] for record in skills},
            {"example/device-setup", "example/troubleshoot"},
        )
        self.assertEqual(len({record["source_key"] for record in skills}), 2)

    def test_pathless_seed_enumerates_the_entire_skill_pack(self):
        config = {
            "taxonomy": "missing-taxonomy.yaml",
            "seed_repositories": {
                "skill": [{"repository": "example/realsense-skills"}],
            },
        }
        records, _ = discover(config, self.client)
        self.assertEqual(sum(kind == "skill" for kind, _ in records), 2)

    def test_failed_query_does_not_discard_other_discoveries(self):
        class PartiallyUnavailableClient(FakeGitHubClient):
            def search(self, kind, query, per_page):
                if query == "broken":
                    raise TimeoutError("upstream timeout")
                return super().search(kind, query, per_page)

        errors = []
        records, _ = discover({
            "taxonomy": "missing.yaml", "skill_repositories": ["broken", "robot skills"],
            "seed_repositories": {"mcp": ["missing/repo"]},
        }, PartiallyUnavailableClient(self.repo, self.paths), errors)
        self.assertEqual(sum(kind == "skill" for kind, _ in records), 2)
        self.assertEqual(len(errors), 2)
        self.assertTrue(all("/tree/main/" in record["url"] for _, record in records))

    def test_skill_cap_rotates_past_first_directory(self):
        first = skill_results_from_repository(self.client, self.repo, max_skills=1)
        second = skill_results_from_repository(self.client, self.repo, max_skills=1, offset=1)
        self.assertNotEqual(first[0]["path"], second[0]["path"])

    def test_truncated_tree_is_reported_instead_of_silently_accepted(self):
        class TruncatedClient(FakeGitHubClient):
            def get(self, path, params=None):
                result = super().get(path, params)
                if "tree" in result:
                    result["truncated"] = True
                return result

        with self.assertRaisesRegex(ValueError, "truncated"):
            skill_results_from_repository(TruncatedClient(self.repo, self.paths), self.repo)

    def test_unchanged_blob_reuses_local_skill_evidence(self):
        result = skill_results_from_repository(self.client, self.repo)[0]
        content = self.client.content(result["url"])
        self.client.skill_content_cache = {result["sha"]: content}

        def unavailable_content(url):
            raise AssertionError("Unchanged blob must not be downloaded again")

        self.client.content = unavailable_content
        record = skill_record(self.client, result, "robot skills")
        self.assertEqual(record["raw_data"]["skill_content"], content)

    def test_transient_disconnect_is_retried_without_losing_query(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"items": []}'
        with patch("github_discovery.urllib.request.urlopen",
                   side_effect=[RemoteDisconnected("connection closed"), response]) as get:
            with patch("github_discovery.time.sleep"):
                result = GitHubClient("test-only-token").get("/search/code")
        self.assertEqual(result, {"items": []})
        self.assertEqual(get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
