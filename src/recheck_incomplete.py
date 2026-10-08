#!/usr/bin/env python3
"""Recheck relevant GitHub candidates whose repository content is incomplete."""

import argparse
import base64
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from catalog_sync import parse_frontmatter
from database import connect, init_db
from github_discovery import GitHubClient
from reporting import write_json_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data" / "rosclaw_hub.db"


def _raw(value) -> dict:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _repo_parts(url: str):
    parsed = urlparse(url or "")
    parts = parsed.path.strip("/").split("/")
    if parsed.netloc.lower() != "github.com" or len(parts) < 2:
        return None
    return parts[0], parts[1].removesuffix(".git")


def _error_code(exc):
    return getattr(exc, "code", None)


def _review_evidence(row: dict) -> dict:
    evidence = _raw(row.get("review_evidence"))
    return evidence.get("deterministic", evidence)


def bootstrap_content_status(db_path: Path) -> dict:
    """Mark historical GitHub rows whose stored review had no README evidence."""
    init_db(db_path, quiet=True)
    conn = connect(db_path)
    stats = {"marked": 0, "eligible": 0}
    for item_type, table in (("skill", "skills"), ("mcp", "mcps")):
        rows = conn.execute(f"""
            SELECT i.id, i.source_repo, i.raw_data, i.content_status,
                   r.domain_score, r.evidence AS review_evidence
            FROM {table} i
            JOIN candidate_reviews r
              ON r.item_type=? AND r.item_id=i.id
            WHERE i.lifecycle_status='active'
              AND i.source NOT LIKE 'catalog:%'
              AND COALESCE(i.content_status, 'unknown')='unknown'
              AND r.id=(
                  SELECT latest.id FROM candidate_reviews latest
                  WHERE latest.item_type=r.item_type AND latest.item_id=r.item_id
                  ORDER BY latest.reviewed_at DESC, latest.id DESC LIMIT 1
              )
        """, (item_type,)).fetchall()
        for source_row in rows:
            row = dict(source_row)
            evidence = _review_evidence(row)
            raw = _raw(row["raw_data"])
            if (
                evidence.get("has_readme") is not False
                or raw.get("review_readme")
                or not _repo_parts(row["source_repo"])
            ):
                continue
            eligible = bool(
                evidence.get("physical_anchors")
                and not evidence.get("exclusions")
                and not evidence.get("duplicate_of_published_item")
                and row["domain_score"] >= 18
            )
            conn.execute(
                f"UPDATE {table} SET content_status='unchecked', "
                "content_issue='repository_readme_not_verified', "
                "content_recheck_eligible=? WHERE id=?",
                (int(eligible), row["id"]),
            )
            stats["marked"] += 1
            stats["eligible"] += int(eligible)
    conn.commit()
    conn.close()
    return stats


def _repo_summary(repo_data: dict) -> dict:
    return {
        "full_name": repo_data.get("full_name"),
        "stargazers_count": repo_data.get("stargazers_count", 0),
        "forks_count": repo_data.get("forks_count", 0),
        "archived": repo_data.get("archived", False),
        "pushed_at": repo_data.get("pushed_at"),
        "license": repo_data.get("license"),
        "topics": repo_data.get("topics", []),
    }


def _fetch_candidate(client, item_type: str, row: dict) -> dict:
    owner, repo = _repo_parts(row["source_repo"])
    raw = _raw(row["raw_data"])
    try:
        repo_data = client.get(f"/repos/{owner}/{repo}")
    except Exception as exc:
        return {
            "raw": raw,
            "issue": f"repository_unavailable: {exc}",
            "transient": _error_code(exc) != 404,
        }

    raw["review_repo"] = _repo_summary(repo_data)
    readme_found = False
    try:
        readme = client.get(f"/repos/{owner}/{repo}/readme")
        raw["review_readme"] = base64.b64decode(
            readme.get("content", "")
        ).decode("utf-8", errors="replace")[:100_000]
        raw["review_readme_sha"] = readme.get("sha", "")
        readme_found = True
    except Exception as exc:
        if _error_code(exc) != 404:
            return {
                "raw": raw,
                "stars": repo_data.get("stargazers_count", 0),
                "issue": f"readme_fetch_failed: {exc}",
                "transient": True,
            }

    updates = {
        "raw": raw,
        "stars": repo_data.get("stargazers_count", 0),
        "upstream_updated_at": repo_data.get("pushed_at"),
    }
    changed = False
    source_available = True
    if (
        item_type == "skill"
        and row.get("source") == "github-discovery"
        and row.get("source_path")
    ):
        path = f"{row['source_path'].rstrip('/')}/SKILL.md"
        try:
            skill = client.get(f"/repos/{owner}/{repo}/contents/{path}")
            content = base64.b64decode(skill.get("content", "")).decode(
                "utf-8", errors="replace"
            )
            digest = hashlib.sha256(content.encode()).hexdigest()
            changed = digest != row.get("content_hash")
            metadata, _ = parse_frontmatter(content)
            raw["skill_content"] = content
            raw["metadata"] = metadata
            updates.update({
                "content_hash": digest,
                "source_revision": skill.get("sha", row.get("source_revision")),
                "description": str(metadata.get("description", row.get("description") or "")),
                "version": str(metadata.get("version", row.get("version") or "")),
                "license": str(metadata.get("license", row.get("license") or "")),
            })
        except Exception as exc:
            source_available = False
            updates["issue"] = f"skill_file_unavailable: {exc}"
            updates["transient"] = _error_code(exc) != 404
    elif item_type == "mcp" and row.get("source") == "github-discovery":
        identity = f"{repo_data.get('pushed_at', '')}:{repo_data.get('description') or ''}"
        digest = hashlib.sha256(identity.encode()).hexdigest()
        changed = digest != row.get("content_hash")
        updates.update({
            "content_hash": digest,
            "source_revision": repo_data.get("pushed_at", ""),
            "description": repo_data.get("description") or row.get("description") or "",
        })

    updates["raw"] = raw
    updates["changed"] = changed
    updates["complete"] = readme_found and source_available
    if not updates["complete"] and "issue" not in updates:
        updates["issue"] = "missing_repository_readme"
        updates["transient"] = False
    return updates


def recheck_incomplete(
    db_path: Path,
    client,
    interval_days: int = 7,
    now: datetime = None,
    limit: int = None,
    workers: int = 8,
) -> dict:
    init_db(db_path, quiet=True)
    checked_at = now or datetime.now(timezone.utc)
    conn = connect(db_path)
    candidates = []
    for item_type, table in (("skill", "skills"), ("mcp", "mcps")):
        query = f"""
            SELECT * FROM {table}
            WHERE lifecycle_status='active' AND (
                content_status='unchecked' OR (
                    content_recheck_eligible=1 AND content_status='incomplete'
                    AND content_next_check <= ?
                )
            ) ORDER BY COALESCE(content_next_check, first_seen), id
        """
        params = [checked_at.isoformat()]
        if limit is not None:
            query += " LIMIT ?"
            params.append(max(limit - len(candidates), 0))
        candidates.extend((item_type, table, dict(row)) for row in conn.execute(query, params))
        if limit is not None and len(candidates) >= limit:
            break

    stats = {
        "planned": len(candidates), "checked": 0, "completed": 0,
        "still_incomplete": 0, "requeued": 0, "failed": 0, "items": [],
    }
    with ThreadPoolExecutor(max_workers=workers) as executor:
        fetched = list(executor.map(
            lambda candidate: _fetch_candidate(
                client, candidate[0], candidate[2]
            ),
            candidates,
        ))
    for (item_type, table, row), result in zip(candidates, fetched):
        previous_status = row["content_status"]
        complete = bool(result.get("complete"))
        changed = bool(result.get("changed"))
        requeue = changed or (complete and previous_status == "incomplete")
        issue = None if complete else result.get("issue", "content_check_failed")[:500]
        retry_days = 1 if result.get("transient") else interval_days
        next_check = (
            (checked_at + timedelta(days=retry_days)).isoformat()
            if not complete and row["content_recheck_eligible"] else None
        )
        site_status = row["site_status"]
        if requeue:
            site_status = (
                "pending_review_update"
                if row.get("site_id") or site_status == "uploaded"
                else "pending"
            )
        values = {
            "raw_data": json.dumps(
                result.get("raw", _raw(row["raw_data"])),
                ensure_ascii=False, default=str,
            ),
            "stars": result.get("stars", row["stars"]),
            "content_hash": result.get("content_hash", row["content_hash"]),
            "source_revision": result.get("source_revision", row["source_revision"]),
            "description": result.get("description", row["description"]),
            "version": result.get("version", row["version"]),
            "license": result.get("license", row["license"]),
            "upstream_updated_at": result.get("upstream_updated_at", row["upstream_updated_at"]),
        }
        conn.execute(f"""
            UPDATE {table} SET raw_data=:raw_data, stars=:stars,
                content_hash=:content_hash, source_revision=:source_revision,
                description=:description, version=:version, license=:license,
                upstream_updated_at=:upstream_updated_at,
                content_status=:content_status, content_issue=:content_issue,
                content_last_checked=:content_last_checked,
                content_next_check=:content_next_check,
                content_check_count=COALESCE(content_check_count, 0) + 1,
                decision=CASE WHEN :requeue THEN 'review' ELSE decision END,
                reason=CASE WHEN :requeue THEN
                    'Repository content changed during scheduled completeness recheck.'
                    ELSE reason END,
                site_status=:site_status,
                content_recheck_eligible=CASE WHEN :complete THEN 0
                    ELSE content_recheck_eligible END
            WHERE id=:id
        """, {
            **values,
            "content_status": "complete" if complete else "incomplete",
            "content_issue": issue,
            "content_last_checked": checked_at.isoformat(),
            "content_next_check": next_check,
            "requeue": int(requeue),
            "site_status": site_status,
            "complete": int(complete),
            "id": row["id"],
        })
        stats["checked"] += 1
        stats["completed" if complete else "still_incomplete"] += 1
        stats["requeued"] += int(requeue)
        stats["failed"] += int(bool(result.get("transient")))
        stats["items"].append({
            "item_type": item_type, "item_id": row["id"],
            "full_name": row["full_name"], "status": "complete" if complete else "incomplete",
            "issue": issue, "requeued": requeue, "next_check": next_check,
        })
    conn.commit()
    conn.close()
    return stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--interval-days", type=int, default=7)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument(
        "--report", type=Path,
        default=PROJECT_ROOT / "data" / "reports" / "incomplete_recheck.json",
    )
    args = parser.parse_args(argv)
    if args.interval_days < 1:
        parser.error("--interval-days must be at least 1")
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        parser.error("GITHUB_TOKEN is required")
    output = {}
    if args.bootstrap:
        output["bootstrap"] = bootstrap_content_status(args.db)
    output["recheck"] = recheck_incomplete(
        args.db, GitHubClient(token), args.interval_days, limit=args.limit,
        workers=args.workers,
    )
    write_json_report(args.report, output)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
