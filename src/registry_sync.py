#!/usr/bin/env python3
"""Discover physical-AI MCP servers from the official MCP Registry."""

import argparse
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, Optional

import yaml

from database import insert_item, record_source_sync, utc_now


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "sources.yaml"
USER_AGENT = "rosclaw-crawler/3.0 (+https://github.com/ros-claw/rosclaw-crawler)"


def fetch_json(url: str, timeout: int = 30, attempts: int = 2) -> dict:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    last_error = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504):
                raise
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
        except (TimeoutError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
    raise last_error


def search_registry(
    endpoint: str,
    keywords: Iterable[str],
    max_pages: int = 100,
    page_size: int = 100,
    errors: Optional[list] = None,
    workers: int = 3,
) -> Dict[str, dict]:
    """Search each domain keyword and retain only the latest server version."""
    latest = {}
    errors = errors if errors is not None else []

    def search_keyword(keyword):
        matches = {}
        cursor: Optional[str] = None
        seen_cursors = set()
        for _ in range(max_pages):
            params = {"limit": page_size, "search": keyword}
            if cursor:
                params["cursor"] = cursor
            try:
                payload = fetch_json(f"{endpoint}?{urllib.parse.urlencode(params)}")
            except Exception as exc:
                # Keep completed pages even if a later page fails.
                errors.append({"keyword": keyword, "error": str(exc), "cursor": cursor})
                return matches
            for entry in payload.get("servers", []):
                server = entry.get("server", {})
                metadata = entry.get("_meta", {}).get(
                    "io.modelcontextprotocol.registry/official", {}
                )
                if not metadata.get("isLatest", False):
                    continue
                name = server.get("name")
                if not name:
                    continue
                existing = matches.get(name)
                if not existing or metadata.get("updatedAt", "") > existing[1].get("updatedAt", ""):
                    matches[name] = (entry, metadata, keyword)
            cursor = payload.get("metadata", {}).get("nextCursor")
            if not cursor:
                break
            if cursor in seen_cursors:
                errors.append({"keyword": keyword, "error": "repeated pagination cursor"})
                return matches
            seen_cursors.add(cursor)
        else:
            errors.append({"keyword": keyword, "error": "pagination limit reached",
                           "cursor": cursor})
        return matches

    keyword_list = list(keywords)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(keyword_list) or 1))) as executor:
        futures = {
            executor.submit(search_keyword, keyword): keyword for keyword in keyword_list
        }
        for future in as_completed(futures):
            keyword = futures[future]
            try:
                matches = future.result()
            except Exception as exc:
                errors.append({"keyword": keyword, "error": str(exc)})
                continue
            for name, candidate in matches.items():
                existing = latest.get(name)
                if not existing or candidate[1].get("updatedAt", "") > existing[1].get("updatedAt", ""):
                    latest[name] = candidate
    return {name: value[0] | {"_matchedKeyword": value[2]} for name, value in latest.items()}


def _server_url(server: dict, registry_url: str) -> str:
    repository = server.get("repository") or {}
    if repository.get("url"):
        return repository["url"]
    remotes = server.get("remotes") or []
    if remotes and remotes[0].get("url"):
        return remotes[0]["url"]
    return f"{registry_url}?q={urllib.parse.quote(server.get('name', ''))}"


def build_record(source_key: str, source: dict, entry: dict) -> dict:
    server = entry["server"]
    official = entry.get("_meta", {}).get(
        "io.modelcontextprotocol.registry/official", {}
    )
    canonical = json.dumps(server, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    name = server["name"]
    tags = ["official-mcp-registry", entry.get("_matchedKeyword", "")]
    return {
        "source": source_key,
        "source_key": f"registry:{source_key}:{name}",
        "source_repo": (server.get("repository") or {}).get("url", ""),
        "source_revision": server.get("version", ""),
        "content_hash": digest,
        "name": server.get("title") or name.split("/")[-1],
        "full_name": name,
        "description": server.get("description", ""),
        "url": _server_url(server, source.get("source_url", source["endpoint"])),
        "topics": [tag for tag in tags if tag],
        "decision": "review",
        "reason": (
            "Matched physical-AI keyword in the official MCP Registry: "
            f"{entry.get('_matchedKeyword', '')}"
        ),
        "confidence": 65,
        "site_status": "pending",
        "version": server.get("version", ""),
        "upstream_updated_at": official.get("updatedAt"),
        "raw_data": entry,
    }


def sync_registry(source_key: str, source: dict, db_path: Path, dry_run=False) -> dict:
    started_at = utc_now()
    keyword_errors = []
    entries = search_registry(
        source["endpoint"],
        source.get("keywords", []),
        source.get("max_pages", 100),
        errors=keyword_errors,
        workers=source.get("workers", 3),
    )
    records = [build_record(source_key, source, entries[name]) for name in sorted(entries)]
    stats = {
        "source": source_key,
        "started_at": started_at,
        "revision": utc_now(),
        "discovered": len(records),
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "missing": 0,
        "status": "dry-run" if dry_run else ("partial" if keyword_errors else "complete"),
        "details": {"keyword_errors": keyword_errors},
        "items": records if dry_run else [],
    }
    if dry_run:
        return stats
    for record in records:
        result = insert_item("mcp", record, db_path)
        stats[result] += 1
    record_source_sync(source_key, stats, db_path)
    return stats


def load_sources(path: Path = DEFAULT_CONFIG) -> Dict[str, dict]:
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return config.get("mcp_registries", {})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="official-mcp-registry")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "data" / "rosclaw_hub.db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    sources = load_sources(args.config)
    if args.source not in sources:
        parser.error(f"unknown registry source: {args.source}")
    try:
        stats = sync_registry(args.source, sources[args.source], args.db, args.dry_run)
    except Exception as exc:
        print(f"registry sync failed: {exc}", file=sys.stderr)
        return 1
    output = stats if args.json else {k: v for k, v in stats.items() if k != "items"}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
