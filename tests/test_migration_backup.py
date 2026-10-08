import json
import sqlite3
import tarfile

import pytest

from migration_backup import create_backup, sha256


def test_backup_snapshots_database_and_preserves_uncommitted_files(tmp_path):
    root = tmp_path / "crawler"
    (root / "data").mkdir(parents=True)
    with sqlite3.connect(root / "data/rosclaw_hub.db") as conn:
        for table in ("skills", "mcps"):
            conn.execute(f"CREATE TABLE {table} (decision TEXT)")
            conn.execute(f"INSERT INTO {table} VALUES ('keep')")
    (root / "uncommitted.py").write_text("print('preserved')\n")
    (root / ".env").write_text("SECRET=not-for-backup")
    (root / ".env.example").write_text("SECRET=\n")
    result = create_backup(root, tmp_path / "backups")
    archive = tmp_path / "backups" / result["archive"].split("/")[-1]
    assert result["sha256"] == sha256(archive)
    assert archive.stat().st_mode & 0o777 == 0o600
    with tarfile.open(archive) as tar:
        names = tar.getnames()
        assert "rosclaw_crawler/.env" not in names
        assert "rosclaw_crawler/.env.example" in names
        assert "rosclaw_crawler/uncommitted.py" in names
        manifest = json.load(tar.extractfile("BACKUP_MANIFEST.json"))
        assert manifest["counts"]["skills"]["total"] == 1
        data = tar.extractfile("rosclaw_crawler/data/rosclaw_hub.db").read()
    restored = tmp_path / "restored.db"
    restored.write_bytes(data)
    with sqlite3.connect(restored) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_backup_rejects_output_inside_workspace(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        create_backup(tmp_path, tmp_path / "backups")
