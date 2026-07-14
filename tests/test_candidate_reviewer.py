import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from candidate_reviewer import (
    _finalize_llm_review,
    apply_review_decisions,
    load_taxonomy,
    review_candidates,
    review_item,
    validate_llm_verdict,
)
from database import insert_item


class FakeLLMReviewer:
    model = "fake-review-model"

    def __init__(self):
        self.calls = 0

    def review(self, item_type, item, baseline, taxonomy):
        self.calls += 1
        return {
            "decision": "keep",
            "relevance_score": 95,
            "authenticity_score": 95,
            "operational_usefulness_score": 90,
            "maintenance_score": 80,
            "risk_score": 10,
            "confidence": 0.95,
            "categories": ["navigation", "robot-middleware"],
            "summary": "Operates ROS2 Nav2 navigation through an Agent Skill.",
            "reasons": ["Contains a valid SKILL.md.", "Provides an operational workflow."],
            "risks": [],
        }


class CandidateReviewerTest(unittest.TestCase):
    def setUp(self):
        self.taxonomy = load_taxonomy()

    def test_real_ros_mcp_is_recommended(self):
        item = {
            "full_name": "example/ros2-mcp",
            "description": "MCP server for ROS2 robot control, topics, services and actions",
            "topics": json.dumps(["ros2", "robotics", "mcp-server"]),
            "stars": 50,
            "source_repo": "https://github.com/example/ros2-mcp",
            "raw_data": json.dumps({
                "review_readme": "Built with FastMCP. Provides robot control and Nav2 navigation tools.",
                "license": "Apache-2.0",
            }),
        }
        review = review_item("mcp", item, self.taxonomy)
        self.assertEqual(review["recommendation"], "keep")
        self.assertIn("robot-middleware", review["categories"])

    def test_generic_spreadsheet_mcp_is_removed(self):
        item = {
            "full_name": "example/sheets-mcp",
            "description": "MCP server to manipulate Google Sheets spreadsheets",
            "topics": "[]",
            "stars": 100,
            "source_repo": "https://github.com/example/sheets-mcp",
            "raw_data": "{}",
        }
        review = review_item("mcp", item, self.taxonomy)
        self.assertEqual(review["recommendation"], "remove")

    def test_installable_robot_skill_is_recommended(self):
        content = """---
name: robot-navigation
description: Operate Nav2 robot navigation through ROS2 actions.
---
# Robot navigation
## Workflow
Use scripts/navigate.py to send Nav2 goals and inspect localization.
""" + ("Safe operational guidance. " * 30)
        item = {
            "full_name": "example/robot-navigation",
            "description": "Operate Nav2 robot navigation through ROS2 actions.",
            "topics": json.dumps(["robotics"]),
            "stars": 50,
            "source_repo": "https://github.com/example/robot-skills",
            "raw_data": json.dumps({
                "metadata": {"name": "robot-navigation", "description": "Nav2 skill"},
                "skill_content": content,
            }),
        }
        review = review_item("skill", item, self.taxonomy)
        self.assertEqual(review["recommendation"], "keep")

    def test_ai_review_is_cached_and_applied_without_manual_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            db = Path(temporary) / "hub.db"
            content = """---
name: robot-navigation
description: Operate Nav2 robot navigation through ROS2 actions.
---
# Robot navigation
## Workflow
Use scripts/navigate.py to send navigation goals and monitor the robot.
""" + ("Validate robot state and stop safely. " * 30)
            insert_item("skill", {
                "source": "github-discovery",
                "source_key": "github-skill:example/robot-navigation:SKILL.md",
                "source_repo": "https://github.com/example/robot-navigation",
                "content_hash": "content-v1",
                "name": "robot-navigation",
                "full_name": "example/robot-navigation",
                "description": "Operate Nav2 robot navigation through ROS2 actions.",
                "topics": ["ros2", "robotics"],
                "decision": "review",
                "raw_data": {
                    "metadata": {
                        "name": "robot-navigation",
                        "description": "Operate Nav2",
                    },
                    "skill_content": content,
                },
            }, db)
            reviewer = FakeLLMReviewer()
            first = review_candidates(db, self.taxonomy, llm_reviewer=reviewer)
            second = review_candidates(db, self.taxonomy, llm_reviewer=reviewer)
            self.assertEqual(first["summary"]["keep"], 1)
            self.assertEqual(second["summary"]["keep"], 1)
            self.assertEqual(reviewer.calls, 1)

            applied = apply_review_decisions(db)
            self.assertEqual(applied["keep"], 1)
            conn = sqlite3.connect(db)
            decision, site_status = conn.execute(
                "SELECT decision, site_status FROM skills"
            ).fetchone()
            conn.close()
            self.assertEqual((decision, site_status), ("keep", "pending"))

    def test_llm_schema_rejects_unknown_category(self):
        with self.assertRaises(ValueError):
            validate_llm_verdict({
                "decision": "keep",
                "relevance_score": 90,
                "authenticity_score": 90,
                "operational_usefulness_score": 90,
                "maintenance_score": 90,
                "risk_score": 10,
                "confidence": 0.9,
                "categories": ["not-a-real-category"],
                "summary": "A candidate.",
                "reasons": ["Evidence."],
                "risks": [],
            }, {"navigation"})

    def test_llm_ten_point_scores_are_normalized(self):
        verdict = validate_llm_verdict({
            "decision": "keep",
            "relevance_score": 9,
            "authenticity_score": 8,
            "operational_usefulness_score": 9,
            "maintenance_score": 7,
            "risk_score": 2,
            "confidence": 0.9,
            "categories": ["navigation"],
            "summary": "A navigation skill.",
            "reasons": ["Operational evidence."],
            "risks": [],
        }, {"navigation"})
        self.assertEqual(verdict["relevance_score"], 90)
        self.assertEqual(verdict["risk_score"], 20)
        self.assertTrue(verdict["normalized_from_0_10"])

    def test_official_catalog_uses_provenance_aware_thresholds(self):
        baseline = {
            "evidence": {"source_trust": "official-verified"},
            "authenticity_score": 35,
        }
        verdict = {
            "decision": "keep",
            "relevance_score": 95,
            "authenticity_score": 55,
            "operational_usefulness_score": 85,
            "maintenance_score": 60,
            "risk_score": 58,
            "confidence": 0.9,
            "categories": ["simulation-digital-twin"],
            "summary": "Official simulation workflow.",
            "reasons": ["Operational instructions."],
            "risks": [],
        }
        review = _finalize_llm_review(baseline, verdict)
        self.assertEqual(review["recommendation"], "keep")
        self.assertTrue(review["evidence"]["official_verified_policy"])

    def test_verified_community_format_uses_sixty_authenticity_threshold(self):
        baseline = {
            "evidence": {"source_trust": "community"},
            "authenticity_score": 40,
        }
        verdict = {
            "decision": "keep",
            "relevance_score": 92,
            "authenticity_score": 63,
            "operational_usefulness_score": 84,
            "maintenance_score": 52,
            "risk_score": 10,
            "confidence": 0.93,
            "categories": ["robot-middleware"],
            "summary": "Verified ROS2 analysis skill.",
            "reasons": ["Valid skill format and operational workflow."],
            "risks": [],
        }
        review = _finalize_llm_review(baseline, verdict)
        self.assertEqual(review["recommendation"], "keep")
        self.assertEqual(review["evidence"]["thresholds"]["authenticity"], 60)

    def test_official_catalog_without_keyword_anchor_reaches_ai(self):
        with tempfile.TemporaryDirectory() as temporary:
            db = Path(temporary) / "hub.db"
            content = """---
name: hsb-test
description: Run HSB validation workflows.
---
# HSB test
## Workflow
Run scripts/test.py and inspect all validation results.
""" + ("Follow the documented validation sequence. " * 30)
            insert_item("skill", {
                "source": "catalog:official",
                "source_key": "catalog:official:hsb-test",
                "content_hash": "official-v1",
                "name": "hsb-test",
                "full_name": "Official/hsb-test",
                "description": "Run HSB validation workflows.",
                "decision": "review",
                "raw_data": {
                    "trust": "official-verified",
                    "groups": ["Robotics"],
                    "metadata": {"name": "hsb-test", "description": "Validate HSB"},
                    "skill_content": content,
                },
            }, db)
            reviewer = FakeLLMReviewer()
            report = review_candidates(db, self.taxonomy, llm_reviewer=reviewer)
            self.assertEqual(reviewer.calls, 1)
            self.assertEqual(report["summary"]["keep"], 1)

    def test_review_shards_are_disjoint_and_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            db = Path(temporary) / "hub.db"
            for index in range(4):
                content = """---
name: robot-navigation-%d
description: Operate ROS2 Nav2 robot navigation.
---
# Navigation
## Workflow
Use scripts/navigate.py to send navigation goals.
""" % index + ("Validate robot state safely. " * 30)
                insert_item("skill", {
                    "source": "github-discovery",
                    "source_key": f"github:skill:example/navigation-{index}",
                    "content_hash": f"content-{index}",
                    "name": f"robot-navigation-{index}",
                    "full_name": f"example/robot-navigation-{index}",
                    "description": "Operate ROS2 Nav2 robot navigation.",
                    "decision": "review",
                    "raw_data": {
                        "metadata": {
                            "name": f"robot-navigation-{index}",
                            "description": "Operate Nav2",
                        },
                        "skill_content": content,
                    },
                }, db)
            first, second = FakeLLMReviewer(), FakeLLMReviewer()
            report0 = review_candidates(
                db, self.taxonomy, llm_reviewer=first,
                shard_count=2, shard_index=0,
            )
            report1 = review_candidates(
                db, self.taxonomy, llm_reviewer=second,
                shard_count=2, shard_index=1,
            )
            ids0 = {row["item_id"] for row in report0["results"]}
            ids1 = {row["item_id"] for row in report1["results"]}
            self.assertFalse(ids0 & ids1)
            self.assertEqual(len(ids0 | ids1), 4)
            self.assertEqual(first.calls + second.calls, 4)


if __name__ == "__main__":
    unittest.main()
