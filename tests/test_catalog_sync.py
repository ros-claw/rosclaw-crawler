import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from catalog_sync import (
    discover_skill_directories,
    parse_frontmatter,
    selected_skill_names,
    sync_catalog,
)


class CatalogSyncTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "catalog"
        self.db = Path(self.temp.name) / "catalog.db"
        self.root.mkdir()
        self.source = {
            "repository": "https://github.com/example/skills",
            "branch": "main",
            "skills_path": "skills",
            "manifest": "skills.sh.json",
            "include_groups": ["Physical AI", "Robotics"],
            "author": "Example",
            "trust": "official",
            "decision": "keep",
            "confidence": 98,
        }
        self._write_skill("robot-control", "Controls a ROS2 robot", "1.0.0")
        self._write_skill("sim-ready", "Prepares physical AI simulations", "2.0.0")
        self._write_manifest({
            "Physical AI": ["robot-control", "sim-ready"],
            "Robotics": ["robot-control"],
        })

    def tearDown(self):
        self.temp.cleanup()

    def _write_skill(self, name, description, version):
        directory = self.root / "skills" / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n"
            f"version: {version}\nlicense: Apache-2.0\n---\n\n# {name}\n",
            encoding="utf-8",
        )

    def _write_manifest(self, groups):
        payload = {
            "groupings": [
                {"title": title, "skills": skills} for title, skills in groups.items()
            ]
        }
        (self.root / "skills.sh.json").write_text(json.dumps(payload), encoding="utf-8")

    def _row(self, name):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM skills WHERE name=?", (name,)).fetchone()
        conn.close()
        return dict(row)

    def test_frontmatter_requires_name_and_description(self):
        metadata, body = parse_frontmatter(
            "---\nname: test\ndescription: useful\n---\n# Body\n"
        )
        self.assertEqual(metadata["name"], "test")
        self.assertEqual(body, "# Body")
        with self.assertRaises(ValueError):
            parse_frontmatter("# no metadata")
        with self.assertRaises(ValueError):
            parse_frontmatter("---\nname: broken\ndescription: bad: yaml\n---\n")

    def test_group_selection_deduplicates_skills(self):
        manifest = json.loads((self.root / "skills.sh.json").read_text())
        selected = selected_skill_names(manifest, ["Physical AI", "Robotics"])
        self.assertEqual(selected, {"robot-control", "sim-ready"})

    def test_incremental_sync_and_missing_lifecycle(self):
        first = sync_catalog("example", self.source, self.db, self.root)
        self.assertEqual((first["created"], first["discovered"]), (2, 2))
        second = sync_catalog("example", self.source, self.db, self.root)
        self.assertEqual(second["unchanged"], 2)

        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE skills SET site_status='uploaded' WHERE name='robot-control'")
        conn.commit()
        conn.close()
        self._write_skill("robot-control", "Controls a ROS2 robot safely", "1.1.0")
        changed = sync_catalog("example", self.source, self.db, self.root)
        self.assertEqual(changed["updated"], 1)
        self.assertEqual(self._row("robot-control")["site_status"], "pending_review_update")
        self.assertEqual(self._row("robot-control")["decision"], "review")
        self.assertEqual(self._row("robot-control")["version"], "1.1.0")

        self._write_manifest({"Physical AI": ["robot-control"], "Robotics": []})
        missing = sync_catalog("example", self.source, self.db, self.root)
        self.assertEqual(missing["missing"], 1)
        self.assertEqual(self._row("sim-ready")["lifecycle_status"], "missing")

    def test_manifestless_catalog_discovers_skill_directories(self):
        source = {**self.source}
        source.pop("manifest")
        source.pop("include_groups")
        discovered = discover_skill_directories(self.root, "skills")
        self.assertEqual(discovered, {"robot-control": [], "sim-ready": []})

        stats = sync_catalog("directory", source, self.db, self.root)
        self.assertEqual(stats["discovered"], 2)
        self.assertIn(
            "official directory",
            self._row("robot-control")["reason"],
        )


if __name__ == "__main__":
    unittest.main()
