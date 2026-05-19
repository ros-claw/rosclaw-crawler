#!/usr/bin/env python3
"""
Local SQLite database for tracking all crawled and site items.
Tables:
- skills: all discovered skills with classification
- mcps: all discovered mcps with classification
- crawl_runs: record of each crawl execution
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path('/home/ubuntu/rosclaw/rosclaw_crawler/data/rosclaw_hub.db')

def init_db():
    """Initialize database tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,  -- 'github', 'site', 'manual'
            github_id TEXT,
            name TEXT NOT NULL,
            full_name TEXT,
            description TEXT,
            url TEXT,
            stars INTEGER DEFAULT 0,
            language TEXT,
            topics TEXT,
            decision TEXT NOT NULL,  -- 'keep', 'remove', 'review', 'pending'
            reason TEXT,
            confidence REAL,
            site_id TEXT,  -- ID on rosclaw.io if uploaded
            site_status TEXT DEFAULT 'pending',  -- 'pending', 'uploaded', 'deleted', 'skipped'
            first_seen TEXT NOT NULL,
            last_checked TEXT NOT NULL,
            raw_data TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS mcps (
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
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS crawl_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            type TEXT NOT NULL,  -- 'github', 'site_audit'
            query TEXT,
            total_found INTEGER,
            kept INTEGER,
            removed INTEGER,
            reviewed INTEGER,
            details TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS site_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_audit TEXT,
            last_crawl TEXT,
            total_skills INTEGER,
            total_mcps INTEGER,
            quality_score REAL
        )
    ''')

    conn.commit()
    conn.close()
    print(f"Database initialized: {DB_PATH}")


def insert_item(item_type: str, data: dict):
    """Insert or update an item."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    table = 'skills' if item_type == 'skill' else 'mcps'
    now = datetime.now().isoformat()

    # Check if exists
    c.execute(f"SELECT id FROM {table} WHERE full_name = ?", (data.get('full_name', data.get('name')),))
    existing = c.fetchone()

    if existing:
        # Update
        c.execute(f'''
            UPDATE {table} SET
                decision = ?, reason = ?, confidence = ?,
                stars = ?, description = ?, last_checked = ?,
                site_status = ?, site_id = ?, raw_data = ?
            WHERE id = ?
        ''', (
            data.get('decision', 'pending'),
            data.get('reason', ''),
            data.get('confidence', 0),
            data.get('stars', 0),
            data.get('description', ''),
            now,
            data.get('site_status', 'pending'),
            data.get('site_id', ''),
            json.dumps(data, ensure_ascii=False),
            existing[0]
        ))
    else:
        # Insert
        c.execute(f'''
            INSERT INTO {table}
            (source, github_id, name, full_name, description, url, stars, language,
             topics, decision, reason, confidence, site_id, site_status,
             first_seen, last_checked, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('source', 'unknown'),
            data.get('github_id', ''),
            data.get('name', ''),
            data.get('full_name', data.get('name', '')),
            data.get('description', ''),
            data.get('url', ''),
            data.get('stars', 0),
            data.get('language', ''),
            json.dumps(data.get('topics', [])),
            data.get('decision', 'pending'),
            data.get('reason', ''),
            data.get('confidence', 0),
            data.get('site_id', ''),
            data.get('site_status', 'pending'),
            now, now,
            json.dumps(data, ensure_ascii=False)
        ))

    conn.commit()
    conn.close()


def get_items(item_type: str, decision=None, site_status=None, limit=None):
    """Query items from database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    table = 'skills' if item_type == 'skill' else 'mcps'
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
        query += f" LIMIT {limit}"

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def record_crawl_run(crawl_type, query, total, kept, removed, reviewed, details=''):
    """Record a crawl execution."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO crawl_runs (timestamp, type, query, total_found, kept, removed, reviewed, details)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (datetime.now().isoformat(), crawl_type, query, total, kept, removed, reviewed, details))
    conn.commit()
    conn.close()


def update_site_state(total_skills, total_mcps, quality_score):
    """Update site state snapshot."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO site_state (id, last_audit, total_skills, total_mcps, quality_score)
        VALUES (1, ?, ?, ?, ?)
    ''', (datetime.now().isoformat(), total_skills, total_mcps, quality_score))
    conn.commit()
    conn.close()


def get_stats():
    """Get database statistics."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    stats = {}
    for table in ['skills', 'mcps']:
        c.execute(f"SELECT COUNT(*) FROM {table}")
        total = c.fetchone()[0]
        c.execute(f"SELECT COUNT(*) FROM {table} WHERE decision = 'keep'")
        kept = c.fetchone()[0]
        c.execute(f"SELECT COUNT(*) FROM {table} WHERE decision = 'remove'")
        removed = c.fetchone()[0]
        c.execute(f"SELECT COUNT(*) FROM {table} WHERE site_status = 'uploaded'")
        uploaded = c.fetchone()[0]
        stats[table] = {'total': total, 'keep': kept, 'remove': removed, 'uploaded': uploaded}

    conn.close()
    return stats


if __name__ == '__main__':
    init_db()
    print("Stats:", get_stats())
