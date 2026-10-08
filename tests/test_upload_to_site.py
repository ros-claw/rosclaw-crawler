import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import requests

from database import insert_item
from upload_to_site import _readme_summary, build_payload, sync_type


class FakeResponse:
    status_code = 200
    content = b"{}"
    text = "{}"

    def json(self):
        return {}


class FakeHubClient:
    def __init__(self):
        self.updated = []
        self.created = []
        self.deleted = []

    def list_items(self, item_type):
        return [{
            "id": "site-123",
            "name": "NVIDIA/robot-control",
            "githubRepoUrl": "https://github.com/NVIDIA/skills/tree/main/skills/robot-control",
        }]

    def update(self, item_type, site_id, payload):
        self.updated.append((item_type, site_id, payload))
        return FakeResponse()

    def create(self, item_type, payload):
        self.created.append((item_type, payload))
        return FakeResponse()

    def delete(self, item_type, site_id):
        self.deleted.append((item_type, site_id))
        return FakeResponse()


class UploadToSiteTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "hub.db"
        self.record = {
            "source": "catalog:nvidia-skills",
            "source_key": "catalog:nvidia-skills:robot-control",
            "source_repo": "https://github.com/NVIDIA/skills",
            "source_path": "skills/robot-control",
            "source_revision": "abc123",
            "content_hash": "hash-v2",
            "name": "robot-control",
            "full_name": "NVIDIA/robot-control",
            "description": "Control a ROS2 robot",
            "url": "https://github.com/NVIDIA/skills/tree/main/skills/robot-control",
            "topics": ["Robotics", "ros2"],
            "decision": "keep",
            "version": "1.2.0",
            "license": "Apache-2.0",
            "raw_data": {
                "groups": ["Robotics"],
                "metadata": {"name": "robot-control", "description": "Control"},
                "skill_content": "---\nname: robot-control\n---\n",
            },
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_payload_uses_individual_skill_identity(self):
        payload = build_payload("skill", self.record)
        self.assertEqual(payload["name"], "NVIDIA/robot-control")
        self.assertEqual(payload["category"], "Robotics")
        self.assertEqual(payload["version"], "1.2.0")
        self.assertIn("name: robot-control", payload["readme_content"])

    def test_readme_summary_skips_badges_and_headings(self):
        summary = _readme_summary({
            "review_readme": "![hero](hero.svg)\n# Title\n\n> Control and monitor a fleet of industrial PLC devices safely.\n"
        })
        self.assertEqual(
            summary, "Control and monitor a fleet of industrial PLC devices safely."
        )

    def test_pending_update_uses_item_put_and_marks_uploaded(self):
        insert_item("skill", self.record, self.db)
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE skills SET site_status='pending_update'")
        conn.commit()
        conn.close()

        client = FakeHubClient()
        stats = sync_type("skill", self.db, client)
        self.assertEqual(stats["updated"], 1)
        self.assertEqual(client.updated[0][1], "site-123")
        self.assertEqual(client.created, [])

        conn = sqlite3.connect(self.db)
        status, site_id = conn.execute(
            "SELECT site_status, site_id FROM skills"
        ).fetchone()
        conn.close()
        self.assertEqual((status, site_id), ("uploaded", "site-123"))

    def test_pending_delete_removes_remote_item(self):
        insert_item("skill", self.record, self.db)
        conn = sqlite3.connect(self.db)
        conn.execute(
            "UPDATE skills SET decision='remove', site_status='pending_delete', "
            "site_id='site-123'"
        )
        conn.commit()
        conn.close()

        client = FakeHubClient()
        stats = sync_type("skill", self.db, client)
        self.assertEqual(stats["deleted"], 1)
        self.assertEqual(client.deleted, [("skill", "site-123")])

        conn = sqlite3.connect(self.db)
        status, site_id = conn.execute(
            "SELECT site_status, site_id FROM skills"
        ).fetchone()
        conn.close()
        self.assertEqual((status, site_id), ("removed", ""))

    def test_hub_outage_preserves_queue_and_reports_failed_items(self):
        insert_item("skill", self.record, self.db)

        class UnavailableHub(FakeHubClient):
            def list_items(self, item_type):
                raise requests.HTTPError("503 Service Unavailable")

        stats = sync_type("skill", self.db, UnavailableHub())
        self.assertEqual(stats["planned"], 1)
        self.assertEqual(stats["failed"], 1)
        self.assertIn("503", stats["error"])
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT site_status FROM skills"
            ).fetchone()[0], "pending")

    def test_empty_queue_does_not_call_unavailable_hub(self):
        class UnavailableHub(FakeHubClient):
            def list_items(self, item_type):
                raise AssertionError("No remote listing needed for an empty queue")

        insert_item("skill", self.record, self.db)
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE skills SET site_status='uploaded'")
        stats = sync_type("skill", self.db, UnavailableHub())
        self.assertEqual(stats["planned"], 0)
        self.assertEqual(stats["failed"], 0)


if __name__ == "__main__":
    unittest.main()
