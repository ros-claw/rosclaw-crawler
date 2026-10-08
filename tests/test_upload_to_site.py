import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

import requests

from database import insert_item
from upload_to_site import _readme_summary, build_payload, github_item_url, sync_type


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
    def test_historical_skill_directory_url_preserves_commit_ref(self):
        item = {
            "url": "https://github.com/example/skills/blob/commit-sha/skills/robot",
            "source_path": "skills/robot", "source_revision": "file-blob-sha",
        }
        self.assertEqual(github_item_url("skill", item),
                         "https://github.com/example/skills/tree/commit-sha/skills/robot")
        self.assertEqual(github_item_url("mcp", item), item["url"])

    def test_file_url_remains_valid_and_branch_slashes_are_preserved(self):
        item = {"url": "https://github.com/example/skills/blob/feature/robot/skills/nav",
                "source_path": "skills/nav"}
        self.assertEqual(github_item_url("skill", item),
                         "https://github.com/example/skills/tree/feature/robot/skills/nav")
        item["url"] += "/SKILL.md"
        self.assertEqual(github_item_url("skill", item), item["url"])

    def test_historical_root_blob_without_file_becomes_repository_url(self):
        item = {"url": "https://github.com/example/skills/blob/commit-sha", "source_path": "."}
        self.assertEqual(github_item_url("skill", item), "https://github.com/example/skills")

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

    def test_completed_upload_survives_later_interruption(self):
        insert_item("skill", self.record, self.db)
        insert_item("skill", {
            **self.record, "source_key": "second", "full_name": "example/second",
            "url": "https://github.com/example/second",
        }, self.db)

        class InterruptedHub(FakeHubClient):
            def create(self, item_type, payload):
                raise RuntimeError("process interrupted")

        with self.assertRaises(RuntimeError):
            sync_type("skill", self.db, InterruptedHub())
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT site_status FROM skills WHERE source_key=?",
                (self.record["source_key"],),
            ).fetchone()[0], "uploaded")

    def test_delete_already_missing_remote_is_success(self):
        insert_item("skill", self.record, self.db)
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE skills SET decision='remove', "
                         "site_status='pending_delete', site_id='site-123'")

        class MissingHub(FakeHubClient):
            def delete(self, item_type, site_id):
                response = FakeResponse()
                response.status_code = 404
                return response

        stats = sync_type("skill", self.db, MissingHub())
        self.assertEqual(stats["failed"], 0)
        self.assertEqual(stats["deleted"], 1)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT site_status FROM skills"
            ).fetchone()[0], "removed")

    def test_parallel_writes_are_independent_and_checkpointed(self):
        for index in range(2):
            insert_item("skill", {
                **self.record, "source_key": f"parallel-{index}",
                "full_name": f"example/parallel-{index}",
                "url": f"https://github.com/example/parallel-{index}",
            }, self.db)
        barrier = threading.Barrier(2)

        class ParallelHub(FakeHubClient):
            def create(self, item_type, payload):
                barrier.wait(timeout=5)
                return super().create(item_type, payload)

        stats = sync_type("skill", self.db, ParallelHub(), workers=2)
        self.assertEqual(stats["created"], 2)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM skills WHERE site_status='uploaded'"
            ).fetchone()[0], 2)

    def test_same_url_is_serialized_and_reuses_created_identity(self):
        for index in range(2):
            insert_item("skill", {
                **self.record, "source_key": f"shared-{index}",
                "full_name": f"example/shared-{index}",
            }, self.db)

        class CreatedResponse(FakeResponse):
            def json(self):
                return {"id": "new-site-id"}

        class SharedHub(FakeHubClient):
            def list_items(self, item_type):
                return []

            def create(self, item_type, payload):
                self.created.append(payload)
                return CreatedResponse()

        client = SharedHub()
        stats = sync_type("skill", self.db, client, workers=4)
        self.assertEqual(stats["created"], 1)
        self.assertEqual(stats["updated"], 1)
        self.assertEqual(client.updated[0][1], "new-site-id")

    def test_inflight_source_change_is_not_marked_uploaded(self):
        insert_item("skill", self.record, self.db)
        database = self.db

        class ChangedSourceHub(FakeHubClient):
            def update(self, item_type, site_id, payload):
                with sqlite3.connect(database) as conn:
                    conn.execute("UPDATE skills SET decision='review', "
                                 "content_hash='new-content', site_status='pending_review_update'")
                return FakeResponse()

        stats = sync_type("skill", self.db, ChangedSourceHub())
        self.assertEqual(stats["updated"], 1)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute(
                "SELECT decision, site_status, site_id FROM skills"
            ).fetchone(), ("review", "pending_review_update", "site-123"))

    def test_known_site_id_is_used_when_listing_is_capped(self):
        insert_item("skill", self.record, self.db)
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE skills SET site_id='known-id', site_status='pending_update'")

        class CappedHub(FakeHubClient):
            def list_items(self, item_type):
                return []

        client = CappedHub()
        stats = sync_type("skill", self.db, client)
        self.assertEqual(stats["updated"], 1)
        self.assertEqual(client.updated[0][1], "known-id")
        self.assertEqual(client.created, [])

    def test_duplicate_create_resolves_existing_item_outside_listing(self):
        insert_item("skill", self.record, self.db)

        class CappedHub(FakeHubClient):
            def list_items(self, item_type):
                return []

            def create(self, item_type, payload):
                response = FakeResponse()
                response.status_code = 409
                response.text = "Skill already exists"
                return response

            def find(self, item_type, name):
                return {"id": "outside-list"}

        client = CappedHub()
        stats = sync_type("skill", self.db, client)
        self.assertEqual(stats["updated"], 1)
        self.assertEqual(stats["failed"], 0)
        self.assertEqual(client.updated[0][1], "outside-list")


if __name__ == "__main__":
    unittest.main()
