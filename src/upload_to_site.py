#!/usr/bin/env python3
"""Create and update approved ROSClaw Hub entries from the local database."""

import argparse
import fcntl
import json
import os
import re
import sqlite3
import sys
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

import requests

from database import connect, init_db
from reporting import write_json_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data" / "rosclaw_hub.db"
DEFAULT_BASE_URL = (
    os.getenv("ROSCLAW_BASE_URL")
    or os.getenv("ROSCALW_BASE_URL")
    or "https://www.rosclaw.io"
).rstrip("/")
CATEGORY_LABELS = {
    "robot-middleware": "Robot Middleware",
    "hardware-control": "Robot Control",
    "manipulation": "Manipulation",
    "navigation": "Navigation and SLAM",
    "perception": "Robot Perception",
    "spatial-intelligence": "Spatial Intelligence",
    "simulation-digital-twin": "Simulation and Digital Twin",
    "embodied-learning": "VLA and Robot Learning",
    "data-flywheel": "Robot Data and Evaluation",
    "safety-validation": "Safety and Validation",
    "diagnostics-calibration": "Diagnostics and Calibration",
    "edge-deployment": "Edge Deployment",
    "aerial-autonomy": "Drones and Aerial Autonomy",
    "autonomous-vehicles": "Autonomous Vehicles",
    "industrial-automation": "Industrial Automation",
    "robot-platforms": "Robot Platforms",
    "fabrication": "Agentic Fabrication",
    "human-robot-interaction": "Human-Robot Interaction",
}


def _json_value(value, fallback):
    if not value:
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _owner_from_item(item: dict) -> str:
    raw = _json_value(item.get("raw_data"), {})
    metadata = raw.get("metadata", {}) if isinstance(raw, dict) else {}
    author = metadata.get("metadata", {}).get("author")
    if author:
        return str(author)
    repository = item.get("source_repo") or item.get("url") or ""
    path = urlparse(repository).path.strip("/").split("/")
    return path[0] if path and path[0] else item["full_name"].split("/")[0]


def _readme_summary(raw: dict) -> str:
    readme = raw.get("review_readme") or raw.get("skill_content") or ""
    in_code = False
    for line in readme.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if (
            in_code or not stripped or stripped.startswith(("#", "![", "[![", "|", "---"))
        ):
            continue
        stripped = stripped.lstrip("> ")
        stripped = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", stripped)
        if len(stripped) >= 40:
            return stripped[:500]
    return ""


def build_payload(item_type: str, item: dict) -> dict:
    raw = _json_value(item.get("raw_data"), {})
    metadata = raw.get("metadata", {}) if isinstance(raw, dict) else {}
    topics = _json_value(item.get("topics"), [])
    author = _owner_from_item(item)
    full_name = item.get("full_name") or f"{author}/{item['name']}"
    description = (
        item.get("description") or _readme_summary(raw)
        or f"{'Agent Skill' if item_type == 'skill' else 'MCP server'} for {full_name}"
    )
    review_categories = raw.get("review_categories") or []
    category = (
        CATEGORY_LABELS.get(review_categories[0], review_categories[0])
        if review_categories else (raw.get("groups") or ["General"])[0]
    )
    base = {
        "name": full_name,
        "display_name": item.get("name") or full_name.split("/")[-1],
        "description": description,
        "long_description": raw.get("skill_card") or description,
        "readme_content": raw.get("skill_content") or "",
        "github_repo_url": item.get("url") or item.get("source_repo") or "",
        "author_name": author,
        "category": category,
        "tags": topics,
        "version": item.get("version") or "1.0.0",
        "github_stars": item.get("stars") or 0,
    }
    if item_type == "skill":
        compatibility = metadata.get("compatibility", "")
        base.update({
            "robot_types": ["universal"],
            "compatible_robots": [],
            "dependencies": [compatibility] if compatibility else [],
        })
    else:
        server = raw.get("server", {}) if isinstance(raw, dict) else {}
        base.update({
            "robot_type": "universal",
            "tools": [],
            "install_command": _install_command(server),
        })
    return base


def _install_command(server: dict) -> str:
    packages = server.get("packages") or []
    if not packages:
        return ""
    package = packages[0]
    identifier = package.get("identifier", "")
    registry_type = package.get("registryType")
    if registry_type == "npm":
        return f"npx -y {identifier}"
    if registry_type == "pypi":
        return f"uvx {identifier}"
    return ""


class HubClient:
    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL):
        if not api_key:
            raise ValueError("ROSCLAW_API_KEY is required")
        self.base_url = base_url.rstrip("/")
        self._sessions = threading.local()
        self.headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key,
            "User-Agent": "rosclaw-crawler/3.0",
        }

    @property
    def session(self):
        if not hasattr(self._sessions, "session"):
            self._sessions.session = requests.Session()
            self._sessions.session.headers.update(self.headers)
        return self._sessions.session

    @staticmethod
    def endpoint(item_type: str) -> str:
        return "skills" if item_type == "skill" else "mcp-packages"

    def list_items(self, item_type: str) -> list:
        response = self.session.get(
            f"{self.base_url}/api/{self.endpoint(item_type)}?page=1&limit=5000",
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else payload.get("items", payload.get("data", []))

    def create(self, item_type: str, payload: dict) -> requests.Response:
        return self.session.post(
            f"{self.base_url}/api/{self.endpoint(item_type)}",
            json=payload,
            timeout=30,
        )

    def update(self, item_type: str, site_id: str, payload: dict) -> requests.Response:
        return self.session.put(
            f"{self.base_url}/api/{self.endpoint(item_type)}/{site_id}",
            json=payload,
            timeout=30,
        )

    def delete(self, item_type: str, site_id: str) -> requests.Response:
        return self.session.delete(
            f"{self.base_url}/api/{self.endpoint(item_type)}/{site_id}",
            timeout=30,
        )


def _site_identity(item: dict) -> Tuple[str, str]:
    return (
        (item.get("name") or "").lower(),
        (item.get("githubRepoUrl") or item.get("github_repo_url") or "").lower(),
    )


def _upload_batches(rows, item_type, client, by_name, by_url, workers):
    """Parallelize independent writes; serialize rows sharing a Hub identity."""
    pending = deque(rows)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        while pending:
            batch = []
            identities = set()
            while pending and len(batch) < workers:
                row = pending[0]
                payload = None if row["site_status"] == "pending_delete" else build_payload(item_type, row)
                if payload is None:
                    remote = {"id": row["site_id"]} if row.get("site_id") else None
                    keys = {("id", row.get("site_id") or f"local:{row['id']}")}
                    operation = "deleted"
                else:
                    name, url = _site_identity(payload)
                    remote = by_name.get(name) or (by_url.get(url) if url else None)
                    keys = {("name", name)}
                    if url:
                        keys.add(("url", url))
                    if remote:
                        keys.add(("id", remote["id"]))
                    operation = "updated" if remote else "created"
                if identities & keys:
                    break
                identities.update(keys)
                pending.popleft()
                if operation == "deleted":
                    future = executor.submit(client.delete, item_type, remote["id"]) if remote else None
                elif operation == "updated":
                    future = executor.submit(client.update, item_type, remote["id"], payload)
                else:
                    future = executor.submit(client.create, item_type, payload)
                batch.append((row, payload, remote, operation, future))
            yield from batch


def sync_type(
    item_type: str,
    db_path: Path,
    client: Optional[HubClient],
    dry_run: bool = False,
    limit: Optional[int] = None,
    workers: int = 1,
) -> dict:
    table = "skills" if item_type == "skill" else "mcps"
    conn = connect(db_path)
    query = (
        f"SELECT * FROM {table} WHERE lifecycle_status='active' AND ("
        "(decision='keep' AND site_status IN ('pending', 'pending_update')) OR "
        "(decision='remove' AND site_status='pending_delete')) ORDER BY first_seen"
    )
    params = []
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    rows = [dict(row) for row in conn.execute(query, params).fetchall()]
    conn.close()

    stats = {
        "planned": len(rows), "created": 0, "updated": 0,
        "deleted": 0, "failed": 0,
    }
    if dry_run:
        stats["items"] = [
            {
                "operation": (
                    "delete" if row["site_status"] == "pending_delete" else
                    "update" if row["site_status"] == "pending_update" else "create"
                ),
                "payload": None if row["site_status"] == "pending_delete" else build_payload(item_type, row),
            }
            for row in rows
        ]
        return stats
    if client is None:
        raise ValueError("Hub client is required unless --dry-run is used")
    if not rows:
        return stats

    try:
        remote_items = client.list_items(item_type)
    except (requests.RequestException, ValueError) as exc:
        stats["failed"] = len(rows)
        stats["error"] = f"Hub listing unavailable: {exc}"
        print(f"{item_type}: {stats['error']}", file=sys.stderr)
        return stats
    by_name = {}
    by_url = {}
    for remote in remote_items:
        name, url = _site_identity(remote)
        if name:
            by_name[name] = remote
        if url:
            by_url[url] = remote

    conn = connect(db_path)
    for processed, (row, payload, remote, operation, future) in enumerate(
        _upload_batches(rows, item_type, client, by_name, by_url, workers), start=1
    ):
        if processed == 1 or processed % 50 == 0:
            print(f"{item_type} upload progress: {processed}/{len(rows)}", file=sys.stderr)
        try:
            if future is None:
                conn.execute(
                    f"UPDATE {table} SET site_status='removed', site_id='' WHERE id=?",
                    (row["id"],),
                )
                conn.commit()
                continue
            response = future.result()
            if response.status_code not in (200, 201, 204) and not (
                operation == "deleted" and response.status_code == 404
            ):
                stats["failed"] += 1
                print(
                    f"{item_type} {row['full_name']}: HTTP {response.status_code} "
                    f"{response.text[:200]}", file=sys.stderr,
                )
                continue
            if operation == "deleted":
                conn.execute(
                    f"UPDATE {table} SET site_status=CASE WHEN decision='remove' "
                    "THEN 'removed' ELSE 'pending' END, site_id='' WHERE id=?",
                    (row["id"],),
                )
            else:
                result = response.json() if response.content else {}
                site_id = result.get("id") or (remote or {}).get("id") or ""
                conn.execute(
                    f"UPDATE {table} SET site_id=?, site_status=CASE "
                    "WHEN decision='keep' AND content_hash IS ? THEN 'uploaded' "
                    "WHEN decision='remove' THEN 'pending_delete' "
                    "ELSE site_status END WHERE id=?",
                    (site_id, row["content_hash"], row["id"]),
                )
                if site_id:
                    indexed = {"id": site_id, "name": payload["name"],
                               "github_repo_url": payload["github_repo_url"]}
                    name, url = _site_identity(indexed)
                    by_name[name] = indexed
                    if url:
                        by_url[url] = indexed
            # An acknowledged remote write must survive later interruptions.
            conn.commit()
            stats[operation] += 1
        except requests.RequestException as exc:
            stats["failed"] += 1
            print(f"{item_type} {row['full_name']}: {exc}", file=sys.stderr)
    conn.commit()
    conn.close()
    return stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--type", choices=("skill", "mcp", "all"), default="all")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--show-payloads", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")
    lock = args.db.with_suffix(".upload.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock_file = lock.open("a")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another Hub upload is already running", file=sys.stderr)
        return 2
    init_db(args.db, quiet=True)
    try:
        client = None if args.dry_run else HubClient(
            os.getenv("ROSCLAW_API_KEY") or os.getenv("ROSCALW_API_KEY", ""),
            args.base_url,
        )
    except ValueError as exc:
        parser.error(str(exc))

    output = {}
    types = ("skill", "mcp") if args.type == "all" else (args.type,)
    for item_type in types:
        output[item_type] = sync_type(
            item_type, args.db, client, args.dry_run, args.limit, args.workers
        )
        if not args.show_payloads:
            output[item_type].pop("items", None)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if args.report:
        write_json_report(args.report, output)
    return 1 if any(value["failed"] for value in output.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
