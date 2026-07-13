#!/usr/bin/env python3
"""Run all configured ROSClaw discovery sources and write an audit report."""

import argparse
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from catalog_sync import fetch_catalog, sync_catalog
from github_discovery import GitHubClient, sync_github
from registry_sync import sync_registry


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _summary(stats: dict) -> dict:
    return {key: value for key, value in stats.items() if key != "items"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "sources.yaml")
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "data" / "rosclaw_hub.db")
    parser.add_argument("--fetch-catalogs", action="store_true")
    parser.add_argument("--skip-catalogs", action="store_true")
    parser.add_argument("--skip-registry", action="store_true")
    parser.add_argument("--skip-github", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    lock_path = PROJECT_ROOT / "data" / "sync_sources.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = lock_path.open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another source sync is already running", file=sys.stderr)
        return 2

    config = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "sources": {},
        "errors": {},
    }

    if not args.skip_catalogs:
        for source_key, source in config.get("skill_catalogs", {}).items():
            try:
                root = PROJECT_ROOT / source["local_path"]
                if args.fetch_catalogs:
                    root = fetch_catalog(
                        source_key, source, PROJECT_ROOT / "data" / "source_cache"
                    )
                report["sources"][source_key] = _summary(
                    sync_catalog(source_key, source, args.db, root, args.dry_run)
                )
            except Exception as exc:
                report["errors"][source_key] = str(exc)

    if not args.skip_registry:
        for source_key, source in config.get("mcp_registries", {}).items():
            try:
                report["sources"][source_key] = _summary(
                    sync_registry(source_key, source, args.db, args.dry_run)
                )
            except Exception as exc:
                report["errors"][source_key] = str(exc)

    if not args.skip_github:
        token = os.getenv("GITHUB_TOKEN", "")
        if not token:
            report["sources"]["github-discovery"] = {
                "status": "skipped", "reason": "GITHUB_TOKEN is not set"
            }
        else:
            try:
                report["sources"]["github-discovery"] = _summary(
                    sync_github(
                        config.get("github_discovery", {}),
                        GitHubClient(token), args.db, args.dry_run,
                    )
                )
            except Exception as exc:
                report["errors"]["github-discovery"] = str(exc)

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report_path = args.report
    if report_path is None and not args.dry_run:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_path = PROJECT_ROOT / "data" / "reports" / f"source_sync_{stamp}.json"
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        report["report_path"] = str(report_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
