import base64
import hashlib
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from candidate_reviewer import REVIEWER, apply_review_decisions, enrich_readmes
from database import connect, insert_item
from recheck_incomplete import bootstrap_content_status, recheck_incomplete


class APIError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


class FakeGitHubClient:
    def __init__(self, responses):
        self.responses = responses

    def get(self, path):
        response = self.responses[path]
        if isinstance(response, Exception):
            raise response
        return response


def encoded(content, sha="sha-1"):
    return {
        "content": base64.b64encode(content.encode()).decode(),
        "sha": sha,
    }


class IncompleteRecheckTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "hub.db"
        self.content = """---
name: robot-navigation
description: Operate a ROS2 robot with Nav2.
---
# Robot navigation
Use scripts/navigate.py to send a safe navigation goal.
"""
        insert_item("skill", {
            "source": "github-discovery",
            "source_key": "github:skill:example/skills:skills/robot-navigation",
            "source_repo": "https://github.com/example/skills",
            "source_path": "skills/robot-navigation",
            "content_hash": hashlib.sha256(self.content.encode()).hexdigest(),
            "source_revision": "sha-1",
            "name": "robot-navigation",
            "full_name": "example/robot-navigation",
            "description": "Operate a ROS2 robot with Nav2.",
            "decision": "review",
            "raw_data": {"skill_content": self.content},
        }, self.db)

    def tearDown(self):
        self.temp.cleanup()

    def _defer(self):
        conn = connect(self.db)
        conn.execute("""
            UPDATE skills SET decision='remove', site_status='removed',
                content_status='incomplete',
                content_issue='missing_repository_readme',
                content_next_check='2026-07-01T00:00:00+00:00',
                content_recheck_eligible=1
        """)
        conn.commit()
        conn.close()

    def _repo(self):
        return {
            "full_name": "example/skills", "stargazers_count": 2,
            "forks_count": 0, "archived": False,
            "pushed_at": "2026-07-14T00:00:00Z", "license": None,
            "topics": ["robotics"],
        }

    def _row(self):
        conn = connect(self.db)
        row = dict(conn.execute("SELECT * FROM skills").fetchone())
        conn.close()
        return row

    def test_new_readme_requeues_incomplete_candidate(self):
        self._defer()
        client = FakeGitHubClient({
            "/repos/example/skills": self._repo(),
            "/repos/example/skills/readme": encoded("# Robotics skills", "readme-1"),
            "/repos/example/skills/contents/skills/robot-navigation/SKILL.md": encoded(
                self.content
            ),
        })
        report = recheck_incomplete(
            self.db, client, now=datetime(2026, 7, 15, tzinfo=timezone.utc)
        )
        row = self._row()
        self.assertEqual(report["requeued"], 1)
        self.assertEqual(row["decision"], "review")
        self.assertEqual(row["content_status"], "complete")
        self.assertIsNone(row["content_next_check"])

    def test_changed_skill_requeues_even_when_readme_is_still_missing(self):
        self._defer()
        changed = self.content.replace(
            "---\n# Robot navigation",
            "release-date: 2026-07-15\n---\n# Robot navigation",
        ) + "\n## Workflow\nValidate localization before motion.\n"
        client = FakeGitHubClient({
            "/repos/example/skills": self._repo(),
            "/repos/example/skills/readme": APIError("not found", 404),
            "/repos/example/skills/contents/skills/robot-navigation/SKILL.md": encoded(
                changed, "sha-2"
            ),
        })
        report = recheck_incomplete(
            self.db, client, now=datetime(2026, 7, 15, tzinfo=timezone.utc)
        )
        row = self._row()
        self.assertEqual(report["requeued"], 1)
        self.assertEqual(row["decision"], "review")
        self.assertEqual(row["content_status"], "incomplete")
        self.assertEqual(row["content_issue"], "missing_repository_readme")
        self.assertTrue(row["content_next_check"].startswith("2026-07-22"))

    def test_unchanged_missing_readme_only_advances_schedule(self):
        self._defer()
        client = FakeGitHubClient({
            "/repos/example/skills": self._repo(),
            "/repos/example/skills/readme": APIError("not found", 404),
            "/repos/example/skills/contents/skills/robot-navigation/SKILL.md": encoded(
                self.content
            ),
        })
        report = recheck_incomplete(
            self.db, client, now=datetime(2026, 7, 15, tzinfo=timezone.utc)
        )
        row = self._row()
        self.assertEqual(report["requeued"], 0)
        self.assertEqual(row["decision"], "remove")
        self.assertEqual(row["content_check_count"], 1)
        self.assertTrue(row["content_next_check"].startswith("2026-07-22"))

    def test_unrelated_unchecked_item_is_classified_once_without_schedule(self):
        conn = connect(self.db)
        conn.execute("""
            UPDATE skills SET decision='remove', site_status='removed',
                content_status='unchecked', content_recheck_eligible=0
        """)
        conn.commit()
        conn.close()
        client = FakeGitHubClient({
            "/repos/example/skills": self._repo(),
            "/repos/example/skills/readme": APIError("not found", 404),
            "/repos/example/skills/contents/skills/robot-navigation/SKILL.md": encoded(
                self.content
            ),
        })
        now = datetime(2026, 7, 15, tzinfo=timezone.utc)
        first = recheck_incomplete(self.db, client, now=now)
        second = recheck_incomplete(self.db, client, now=now)
        row = self._row()
        self.assertEqual((first["planned"], second["planned"]), (1, 0))
        self.assertEqual(row["content_status"], "incomplete")
        self.assertIsNone(row["content_next_check"])

    def test_bootstrap_marks_relevant_historical_missing_readme(self):
        conn = connect(self.db)
        item_id = conn.execute("SELECT id FROM skills").fetchone()[0]
        evidence = {
            "physical_anchors": ["robot", "ros2"],
            "exclusions": [],
            "has_readme": False,
        }
        conn.execute("""
            INSERT INTO candidate_reviews (
                item_type, item_id, reviewed_at, reviewer, recommendation,
                score, authenticity_score, domain_score, quality_score,
                risk_score, categories, evidence
            ) VALUES ('skill', ?, ?, 'test', 'remove', 40, 40, 25, 10, 20, '[]', ?)
        """, (item_id, datetime.now(timezone.utc).isoformat(), json.dumps(evidence)))
        conn.commit()
        conn.close()

        report = bootstrap_content_status(self.db)
        row = self._row()
        self.assertEqual(report, {"marked": 1, "eligible": 1})
        self.assertEqual(row["content_status"], "unchecked")
        self.assertEqual(row["content_recheck_eligible"], 1)

    def test_enrichment_failure_is_persisted_and_review_marks_it_eligible(self):
        client = FakeGitHubClient({
            "/repos/example/skills": self._repo(),
            "/repos/example/skills/readme": APIError("not found", 404),
        })
        with patch("candidate_reviewer.GitHubClient", return_value=client):
            report = enrich_readmes(self.db, "test-token", workers=1)
        row = self._row()
        self.assertEqual(report["issues"], {"missing_repository_readme": 1})
        self.assertEqual(row["content_status"], "incomplete")
        self.assertEqual(row["content_check_count"], 1)

        conn = connect(self.db)
        evidence = {
            "physical_anchors": ["robot", "ros2"],
            "exclusions": [],
            "has_readme": False,
        }
        conn.execute("""
            INSERT INTO candidate_reviews (
                item_type, item_id, reviewed_at, reviewer, recommendation,
                score, authenticity_score, domain_score, quality_score,
                risk_score, categories, evidence
            ) VALUES ('skill', ?, ?, ?, 'remove', 40, 40, 25, 10, 20, '[]', ?)
        """, (
            row["id"], datetime.now(timezone.utc).isoformat(), REVIEWER,
            json.dumps(evidence),
        ))
        conn.commit()
        conn.close()
        applied = apply_review_decisions(self.db)
        row = self._row()
        self.assertEqual(applied["incomplete_recheck"], 1)
        self.assertEqual(row["content_recheck_eligible"], 1)
        self.assertIn("7-day recheck", row["reason"])

    def test_bootstrap_excludes_directory_hashed_official_catalogs(self):
        conn = connect(self.db)
        item_id = conn.execute("SELECT id FROM skills").fetchone()[0]
        conn.execute(
            "UPDATE skills SET source='catalog:official', content_hash='directory-hash'"
        )
        conn.execute("""
            INSERT INTO candidate_reviews (
                item_type, item_id, reviewed_at, reviewer, recommendation,
                score, authenticity_score, domain_score, quality_score,
                risk_score, categories, evidence
            ) VALUES ('skill', ?, ?, 'test', 'keep', 80, 40, 25, 15, 5, '[]', ?)
        """, (
            item_id, datetime.now(timezone.utc).isoformat(),
            json.dumps({
                "physical_anchors": ["robot"], "exclusions": [],
                "has_readme": False,
            }),
        ))
        conn.commit()
        conn.close()

        report = bootstrap_content_status(self.db)
        row = self._row()
        self.assertEqual(report, {"marked": 0, "eligible": 0})
        self.assertEqual(row["content_status"], "unknown")


if __name__ == "__main__":
    unittest.main()
