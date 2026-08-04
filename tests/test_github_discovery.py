import unittest

from github_discovery import discover, skill_results_from_repository


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


if __name__ == "__main__":
    unittest.main()
