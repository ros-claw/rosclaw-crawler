#!/usr/bin/env python3
"""SQLite storage for discovered MCP servers and Agent Skills."""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("ROSCLAW_DB_PATH", PROJECT_ROOT / "data" / "rosclaw_hub.db"))
PathLike = Union[str, Path]


CATALOG_COLUMNS = {
    "source_key": "TEXT",
    "source_repo": "TEXT",
    "source_path": "TEXT",
    "source_revision": "TEXT",
    "content_hash": "TEXT",
    "version": "TEXT",
    "license": "TEXT",
    "upstream_updated_at": "TEXT",
    "lifecycle_status": "TEXT DEFAULT 'active'",
    "missing_since": "TEXT",
    "last_synced": "TEXT",
    "content_status": "TEXT DEFAULT 'unknown'",
    "content_issue": "TEXT",
    "content_last_checked": "TEXT",
    "content_next_check": "TEXT",
    "content_check_count": "INTEGER DEFAULT 0",
    "content_recheck_eligible": "INTEGER DEFAULT 0",
}

REVIEW_COLUMNS = {
    "review_hash": "TEXT",
    "model": "TEXT",
    "prompt_version": "TEXT",
    "review_status": "TEXT DEFAULT 'complete'",
    "model_response": "TEXT",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_path(db_path: Optional[PathLike] = None) -> Path:
    return Path(db_path) if db_path else DB_PATH


def connect(db_path: Optional[PathLike] = None) -> sqlite3.Connection:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _add_missing_columns(conn: sqlite3.Connection, table: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, definition in CATALOG_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _add_columns(conn: sqlite3.Connection, table: str, columns: dict) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _json_list(value) -> list:
    # Accept both API arrays and stored JSON, including historical double encoding.
    for _ in range(3):
        if isinstance(value, list):
            return value
        if not isinstance(value, str):
            return []
        try:
            value = json.loads(value or "[]")
        except json.JSONDecodeError:
            return []
    return value if isinstance(value, list) else []


def init_db(db_path: Optional[PathLike] = None, quiet: bool = False) -> None:
    """Create tables and apply idempotent schema migrations."""
    conn = connect(db_path)
    common_columns = """
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        github_id TEXT,
        name TEXT NOT NULL,
        full_name TEXT,
        description TEXT,
        url TEXT,
        stars INTEGER DEFAULT 0,
        language TEXT,
        topics TEXT,
        decision TEXT NOT NULL,
        reason TEXT,
        confidence REAL,
        site_id TEXT,
        site_status TEXT DEFAULT 'pending',
        first_seen TEXT NOT NULL,
        last_checked TEXT NOT NULL,
        raw_data TEXT
    """
    conn.execute(f"CREATE TABLE IF NOT EXISTS skills ({common_columns})")
    conn.execute(f"CREATE TABLE IF NOT EXISTS mcps ({common_columns})")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS crawl_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            type TEXT NOT NULL,
            query TEXT,
            total_found INTEGER,
            kept INTEGER,
            removed INTEGER,
            reviewed INTEGER,
            details TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS site_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_audit TEXT,
            last_crawl TEXT,
            total_skills INTEGER,
            total_mcps INTEGER,
            quality_score REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS source_sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_key TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            source_revision TEXT,
            discovered INTEGER DEFAULT 0,
            created INTEGER DEFAULT 0,
            updated INTEGER DEFAULT 0,
            unchanged INTEGER DEFAULT 0,
            missing INTEGER DEFAULT 0,
            status TEXT NOT NULL,
            details TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS candidate_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_type TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            source_key TEXT,
            reviewed_at TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            recommendation TEXT NOT NULL,
            score REAL NOT NULL,
            authenticity_score REAL NOT NULL,
            domain_score REAL NOT NULL,
            quality_score REAL NOT NULL,
            risk_score REAL NOT NULL,
            categories TEXT NOT NULL,
            evidence TEXT NOT NULL,
            UNIQUE(item_type, item_id, reviewer)
        )
    """)
    _add_columns(conn, "candidate_reviews", REVIEW_COLUMNS)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_candidate_reviews_hash "
        "ON candidate_reviews(item_type, item_id, reviewer, review_hash)"
    )

    for table in ("skills", "mcps"):
        _add_missing_columns(conn, table)
        conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_source_key "
            f"ON {table}(source_key) WHERE source_key IS NOT NULL"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_lifecycle "
            f"ON {table}(lifecycle_status, last_synced)"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_content_recheck "
            f"ON {table}(content_recheck_eligible, content_status, content_next_check)"
        )
    conn.commit()
    conn.close()
    if not quiet:
        print(f"Database initialized: {_db_path(db_path)}")


def insert_item(item_type: str, data: dict, db_path: Optional[PathLike] = None) -> str:
    """Insert or update an item and return created/updated/unchanged."""
    init_db(db_path, quiet=True)
    table = "skills" if item_type == "skill" else "mcps"
    now = utc_now()
    identity = data.get("source_key") or data.get("full_name") or data.get("name")
    identity_column = "source_key" if data.get("source_key") else "full_name"

    conn = connect(db_path)
    existing = conn.execute(
        f"SELECT * FROM {table} WHERE {identity_column} = ?", (identity,)
    ).fetchone()
    if not existing and data.get("source_key") and data.get("full_name"):
        same_name = conn.execute(
            f"SELECT * FROM {table} WHERE lower(full_name)=lower(?) "
            "ORDER BY CASE WHEN source LIKE 'catalog:%' THEN 0 ELSE 1 END, "
            "CASE WHEN site_status='uploaded' THEN 0 ELSE 1 END, id LIMIT 1",
            (data["full_name"],),
        ).fetchone()
        if same_name and str(same_name["source"]).startswith("catalog:") \
                and not str(data.get("source", "")).startswith("catalog:"):
            conn.execute(
                f"UPDATE {table} SET last_checked=?, last_synced=? WHERE id=?",
                (now, now, same_name["id"]),
            )
            conn.commit()
            conn.close()
            return "unchanged"
        existing = same_name

    raw_data = data.get("raw_data", data)
    if not isinstance(raw_data, str):
        raw_data = json.dumps(raw_data, ensure_ascii=False, default=str)

    if existing:
        previous_hash = existing["content_hash"]
        current_hash = data.get("content_hash")
        changed = bool(current_hash and previous_hash != current_hash)
        metadata_changed = any(
            field in data and data[field] != existing[field]
            for field in ("name", "full_name", "url", "stars", "version")
        )
        if not changed:
            previous_raw = json.loads(existing["raw_data"] or "{}")
            incoming_raw = json.loads(raw_data)
            if isinstance(previous_raw, dict) and isinstance(incoming_raw, dict):
                # Review evidence belongs to this content revision, not to a
                # particular discovery response.
                for key, value in previous_raw.items():
                    if key.startswith("review_"):
                        incoming_raw.setdefault(key, value)
                raw_data = json.dumps(incoming_raw, ensure_ascii=False, default=str)
        current_site_status = existing["site_status"] or "pending"
        preserve_decision = existing["decision"] in ("keep", "remove") and not changed
        next_decision = (
            "review" if changed else
            existing["decision"] if preserve_decision else
            data.get("decision", existing["decision"])
        )
        if changed and (current_site_status == "uploaded" or existing["site_id"]):
            current_site_status = "pending_review_update"
        elif changed:
            current_site_status = "pending"
        elif metadata_changed and existing["decision"] == "keep" \
                and current_site_status == "uploaded":
            current_site_status = "pending_update"
        content_status = "unknown" if changed else existing["content_status"]
        content_issue = None if changed else existing["content_issue"]
        content_next_check = None if changed else existing["content_next_check"]
        content_recheck_eligible = (
            0 if changed else existing["content_recheck_eligible"]
        )

        conn.execute(f"""
            UPDATE {table} SET
                source = ?, github_id = ?, name = ?, full_name = ?,
                description = ?, url = ?, stars = ?, language = ?, topics = ?,
                decision = ?, reason = ?, confidence = ?, site_status = ?,
                raw_data = ?, last_checked = ?, source_key = ?, source_repo = ?,
                source_path = ?, source_revision = ?, content_hash = ?, version = ?,
                license = ?, upstream_updated_at = ?, lifecycle_status = 'active',
                missing_since = NULL, last_synced = ?, content_status = ?,
                content_issue = ?, content_next_check = ?,
                content_recheck_eligible = ?
            WHERE id = ?
        """, (
            data.get("source", existing["source"]),
            data.get("github_id", existing["github_id"]),
            data.get("name", existing["name"]),
            data.get("full_name", existing["full_name"]),
            data.get("description", existing["description"]),
            data.get("url", existing["url"]),
            data.get("stars", existing["stars"]),
            data.get("language", existing["language"]),
            json.dumps(_json_list(data.get("topics", existing["topics"]))),
            next_decision,
            existing["reason"] if preserve_decision else data.get("reason", existing["reason"]),
            existing["confidence"] if preserve_decision else data.get("confidence", existing["confidence"]),
            current_site_status,
            raw_data,
            now,
            data.get("source_key", existing["source_key"]),
            data.get("source_repo", existing["source_repo"]),
            data.get("source_path", existing["source_path"]),
            data.get("source_revision", existing["source_revision"]),
            current_hash or previous_hash,
            data.get("version", existing["version"]),
            data.get("license", existing["license"]),
            data.get("upstream_updated_at", existing["upstream_updated_at"]),
            now, content_status, content_issue, content_next_check,
            content_recheck_eligible,
            existing["id"],
        ))
        result = "updated" if changed or metadata_changed else "unchanged"
    else:
        conn.execute(f"""
            INSERT INTO {table} (
                source, github_id, name, full_name, description, url, stars,
                language, topics, decision, reason, confidence, site_id,
                site_status, first_seen, last_checked, raw_data, source_key,
                source_repo, source_path, source_revision, content_hash, version,
                license, upstream_updated_at, lifecycle_status, missing_since,
                last_synced
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?, ?, 'active', NULL, ?)
        """, (
            data.get("source", "unknown"), data.get("github_id", ""),
            data.get("name", ""), data.get("full_name", data.get("name", "")),
            data.get("description", ""), data.get("url", ""),
            data.get("stars", 0), data.get("language", ""),
            json.dumps(_json_list(data.get("topics", []))), data.get("decision", "pending"),
            data.get("reason", ""), data.get("confidence", 0),
            data.get("site_id", ""), data.get("site_status", "pending"),
            now, now, raw_data, data.get("source_key"), data.get("source_repo"),
            data.get("source_path"), data.get("source_revision"),
            data.get("content_hash"), data.get("version"), data.get("license"),
            data.get("upstream_updated_at"), now,
        ))
        result = "created"

    conn.commit()
    conn.close()
    return result


def mark_source_missing(
    item_type: str,
    source_prefix: str,
    active_keys: set,
    db_path: Optional[PathLike] = None,
) -> int:
    """Mark previously synced source items absent from the current snapshot."""
    table = "skills" if item_type == "skill" else "mcps"
    now = utc_now()
    conn = connect(db_path)
    rows = conn.execute(
        f"SELECT id, source_key FROM {table} WHERE source_key LIKE ? "
        "AND lifecycle_status = 'active'",
        (f"{source_prefix}%",),
    ).fetchall()
    missing_ids = [row["id"] for row in rows if row["source_key"] not in active_keys]
    if missing_ids:
        placeholders = ",".join("?" for _ in missing_ids)
        conn.execute(
            f"UPDATE {table} SET lifecycle_status='missing', missing_since=?, "
            f"last_synced=? WHERE id IN ({placeholders})",
            (now, now, *missing_ids),
        )
    conn.commit()
    conn.close()
    return len(missing_ids)


def get_items(
    item_type: str,
    decision=None,
    site_status=None,
    limit=None,
    db_path: Optional[PathLike] = None,
):
    table = "skills" if item_type == "skill" else "mcps"
    conn = connect(db_path)
    query = f"SELECT * FROM {table} WHERE 1=1"
    params = []
    if decision:
        query += " AND decision = ?"
        params.append(decision)
    if site_status:
        query += " AND site_status = ?"
        params.append(site_status)
    query += " ORDER BY stars DESC, last_checked DESC"
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def record_crawl_run(
    crawl_type, query, total, kept, removed, reviewed, details="",
    db_path: Optional[PathLike] = None,
):
    conn = connect(db_path)
    conn.execute("""
        INSERT INTO crawl_runs
        (timestamp, type, query, total_found, kept, removed, reviewed, details)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (utc_now(), crawl_type, query, total, kept, removed, reviewed, details))
    conn.commit()
    conn.close()


def record_source_sync(source_key: str, stats: dict, db_path: Optional[PathLike] = None):
    conn = connect(db_path)
    now = utc_now()
    conn.execute("""
        INSERT INTO source_sync_runs (
            source_key, started_at, finished_at, source_revision, discovered,
            created, updated, unchanged, missing, status, details
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        source_key, stats.get("started_at", now), now, stats.get("revision"),
        stats.get("discovered", 0), stats.get("created", 0),
        stats.get("updated", 0), stats.get("unchanged", 0),
        stats.get("missing", 0), stats.get("status", "complete"),
        json.dumps(stats.get("details", {}), ensure_ascii=False, default=str),
    ))
    conn.commit()
    conn.close()


def update_site_state(total_skills, total_mcps, quality_score, db_path=None):
    conn = connect(db_path)
    conn.execute("""
        INSERT OR REPLACE INTO site_state
        (id, last_audit, total_skills, total_mcps, quality_score)
        VALUES (1, ?, ?, ?, ?)
    """, (utc_now(), total_skills, total_mcps, quality_score))
    conn.commit()
    conn.close()


def get_stats(db_path: Optional[PathLike] = None):
    conn = connect(db_path)
    stats = {}
    for table in ("skills", "mcps"):
        values = {}
        for label, where in (
            ("total", "1=1"), ("keep", "decision='keep'"),
            ("remove", "decision='remove'"),
            ("uploaded", "site_status='uploaded'"),
            ("pending_update", "site_status='pending_update'"),
            ("missing", "lifecycle_status='missing'"),
        ):
            values[label] = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {where}"
            ).fetchone()[0]
        stats[table] = values
    conn.close()
    return stats


if __name__ == "__main__":
    init_db()
    print("Stats:", get_stats())
