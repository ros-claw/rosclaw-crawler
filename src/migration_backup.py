#!/usr/bin/env python3
"""Create a private, consistent crawler backup without credential files."""

import argparse
import fcntl
import hashlib
import json
import os
import sqlite3
import tarfile
import tempfile
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def excluded(path):
    return (
        any(part in {"__pycache__", ".pytest_cache", ".venv", ".ssh", ".codex"} for part in path.parts)
        or (path.name.startswith(".env") and path.name != ".env.example")
        or path.name in {"crawler.env", "credentials.json", "token.json"}
        or path.name.endswith((".lock", ".db-wal", ".db-shm", ".db-journal"))
    )


def create_backup(root, output_directory):
    root = root.resolve()
    output_directory = output_directory.resolve()
    if output_directory == root or root in output_directory.parents:
        raise ValueError("Backup directory must be outside the crawler workspace")
    output_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive = output_directory / f"rosclaw-migration-{stamp}.tar.gz"
    db = root / "data/rosclaw_hub.db"
    with ExitStack() as stack:
        for suffix in ("pipeline", "upload"):
            handle = stack.enter_context((db.parent / f"{db.stem}.{suffix}.lock").open("a"))
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        temporary = Path(stack.enter_context(tempfile.TemporaryDirectory(dir=output_directory)))
        snapshot = temporary / db.name
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as source:
            with sqlite3.connect(snapshot) as target:
                source.backup(target)
                integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    raise RuntimeError(f"Database integrity check failed: {integrity}")
                counts = {
                    table: {
                        "total": target.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                        "decisions": dict(target.execute(
                            f"SELECT decision, COUNT(*) FROM {table} GROUP BY decision"
                        )),
                    } for table in ("skills", "mcps")
                }
        manifest = {
            "created_at": stamp, "workspace": str(root), "counts": counts,
            "database_sha256": sha256(snapshot), "database_integrity": integrity,
            "credentials_included": False,
            "privacy": "Private operational backup, not a sanitized public dataset.",
            "credential_path_to_migrate_separately": "~/.config/rosclaw-crawler/crawler.env",
        }
        metadata = temporary / "BACKUP_MANIFEST.json"
        metadata.write_text(json.dumps(manifest, indent=2) + "\n")
        restore = temporary / "RESTORE.md"
        restore.write_text(
            "# Restore ROSClaw Crawler\n\n"
            "1. Verify the archive against its .sha256 file before extracting.\n"
            "2. Extract into a private directory; the workspace is rosclaw_crawler/.\n"
            "3. Install Python 3 and dependencies: python3 -m pip install -r requirements.txt.\n"
            "4. Recreate ~/.config/rosclaw-crawler/crawler.env with fresh keys; chmod 600 it.\n"
            "   Credential files and Codex authentication are NOT in this archive.\n"
            "5. Check data/rosclaw_hub.db using PRAGMA integrity_check and compare manifest counts.\n"
            "6. Configure and authenticate the review provider on the new machine.\n"
            "7. Adjust WorkingDirectory, ExecStart and EnvironmentFile in deploy/*.service\n"
            "   for the new username and workspace path.\n"
            "8. Link deploy/rosclaw-crawler-sync.service and .timer using systemctl --user link;\n"
            "   run systemctl --user daemon-reload and enable --now rosclaw-crawler-sync.timer.\n"
            "   Enable user lingering if jobs must run while logged out.\n"
            "9. Run systemctl --user start rosclaw-crawler-sync.service and inspect\n"
            "   data/reports/periodic_latest.json before retiring the old machine.\n\n"
            "Keep this archive private: it includes Git history, rejected candidates and logs.\n"
            "A live SQLite backup replaces the main database; caches and older snapshots are included.\n"
        )
        with archive.open("xb") as output:
            os.chmod(archive, 0o600)
            with tarfile.open(fileobj=output, mode="w:gz") as tar:
                tar.add(metadata, arcname="BACKUP_MANIFEST.json")
                tar.add(restore, arcname="RESTORE.md")
                for path in sorted(root.rglob("*")):
                    relative = path.relative_to(root)
                    if excluded(relative) or any(excluded(parent) for parent in relative.parents):
                        continue
                    tar.add(snapshot if path == db else path,
                            arcname=str(Path("rosclaw_crawler") / relative), recursive=False)
    checksum = sha256(archive)
    checksum_file = archive.with_name(archive.name + ".sha256")
    checksum_file.write_text(f"{checksum}  {archive.name}\n")
    os.chmod(checksum_file, 0o600)
    return {"archive": str(archive), "bytes": archive.stat().st_size,
            "sha256": checksum, "manifest": manifest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path,
                        default=PROJECT_ROOT.parent / "migration_backups")
    args = parser.parse_args()
    print(json.dumps(create_backup(PROJECT_ROOT, args.output_directory), indent=2))


if __name__ == "__main__":
    main()
