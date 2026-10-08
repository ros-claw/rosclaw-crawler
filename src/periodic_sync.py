#!/usr/bin/env python3
"""Run independently recoverable crawler stages with a durable health report."""

import argparse
import fcntl
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from database import connect, init_db, utc_now
from reporting import write_json_report as write_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def queue_status(db):
    conn = connect(db)
    try:
        return {
            table: [dict(row) for row in conn.execute(
                f"SELECT decision, site_status, COUNT(*) AS count FROM {table} "
                "WHERE lifecycle_status='active' GROUP BY decision, site_status"
            )] for table in ("skills", "mcps")
        }
    finally:
        conn.close()


def run_stages(stages, report_path, latest_path, db, runner=subprocess.run):
    report = {"started_at": utc_now(), "status": "running", "stages": {}}
    write_report(report_path, report)
    write_report(latest_path, report)
    for name, command, artifact in stages:
        stage = {"started_at": utc_now(), "status": "running", "report": str(artifact)}
        report["stages"][name] = stage
        write_report(report_path, report)
        write_report(latest_path, report)
        print(f"Starting crawler stage: {name}", flush=True)
        try:
            result = runner(command, cwd=PROJECT_ROOT, check=False)
            stage["exit_code"] = result.returncode
            stage["status"] = "complete" if result.returncode == 0 else "failed"
        except OSError as exc:
            stage.update(status="failed", exit_code=1, error=str(exc))
        stage["finished_at"] = utc_now()
        # A failed discovery source must not starve already reviewed uploads.
        write_report(report_path, report)
        write_report(latest_path, report)
    report["finished_at"] = utc_now()
    report["status"] = "complete" if all(
        stage["status"] == "complete" for stage in report["stages"].values()
    ) else "partial"
    report["queues"] = queue_status(db)
    write_report(report_path, report)
    write_report(latest_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "complete" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "data/rosclaw_hub.db")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "sources.yaml")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fetch-catalogs", action="store_true")
    for kind in ("catalogs", "registry", "github"):
        parser.add_argument(f"--skip-{kind}", action="store_true")
    args = parser.parse_args(argv)
    args.db = args.db.resolve()
    args.config = args.config.resolve()
    lock_path = args.db.with_suffix(".pipeline.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = lock_path.open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another crawler pipeline is already running", file=sys.stderr)
        return 2
    init_db(args.db, quiet=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = PROJECT_ROOT / "data/reports/runs" / stamp
    stages = []

    def stage(name, script, options):
        artifact = directory / f"{name}.json"
        stages.append((name, [sys.executable, str(PROJECT_ROOT / "src" / script),
                             "--db", str(args.db), "--report", str(artifact), *options],
                       artifact))

    discovery_options = ["--config", str(args.config)]
    if not args.dry_run or args.fetch_catalogs:
        discovery_options.append("--fetch-catalogs")
    for kind in ("catalogs", "registry", "github"):
        if getattr(args, f"skip_{kind}"):
            discovery_options.append(f"--skip-{kind}")
    if args.dry_run:
        discovery_options.append("--dry-run")
    stage("sources", "sync_sources.py", discovery_options)
    if not args.dry_run:
        stage("incomplete", "recheck_incomplete.py", [])
        stage("review", "candidate_reviewer.py",
              ["--enrich-github", "--llm", "--apply", "--fail-on-retry"])
    stage("upload", "upload_to_site.py", ["--dry-run"] if args.dry_run else [])
    return run_stages(stages, args.report or directory / "pipeline.json",
                      PROJECT_ROOT / "data/reports/periodic_latest.json", args.db)


if __name__ == "__main__":
    raise SystemExit(main())
