#!/usr/bin/env python3
"""Synchronize multi-skill Git repositories into the local ROSClaw catalog."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional, Set, Tuple

import yaml

from database import insert_item, mark_source_missing, record_source_sync, utc_now


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "sources.yaml"


def parse_frontmatter(content: str) -> Tuple[dict, str]:
    """Parse YAML frontmatter from a SKILL.md document."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md is missing YAML frontmatter")
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError("SKILL.md frontmatter is not closed") from exc
    try:
        metadata = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"SKILL.md frontmatter is invalid YAML: {exc}") from exc
    if not isinstance(metadata, dict):
        raise ValueError("SKILL.md frontmatter must be a mapping")
    for required in ("name", "description"):
        if not metadata.get(required):
            raise ValueError(f"SKILL.md frontmatter is missing {required}")
    return metadata, "\n".join(lines[end + 1:]).lstrip()


def selected_skill_names(manifest: dict, groups: Iterable[str]) -> Set[str]:
    return set(selected_skill_groups(manifest, groups))


def selected_skill_groups(manifest: dict, groups: Iterable[str]) -> Dict[str, list]:
    requested = set(groups)
    found = set()
    selected = {}
    for grouping in manifest.get("groupings", []):
        title = grouping.get("title")
        if title in requested:
            found.add(title)
            for skill_name in grouping.get("skills", []):
                selected.setdefault(skill_name, []).append(title)
    missing = requested - found
    if missing:
        raise ValueError(f"manifest groups not found: {', '.join(sorted(missing))}")
    return selected


def discover_skill_directories(root: Path, skills_path: str) -> Dict[str, list]:
    """Discover one-level Agent Skill directories without a catalog manifest."""
    directory = root / skills_path
    if not directory.is_dir():
        raise FileNotFoundError(f"skills directory not found: {directory}")
    return {
        child.name: []
        for child in sorted(directory.iterdir())
        if child.is_dir() and (child / "SKILL.md").is_file()
    }


def content_digest(skill_dir: Path) -> str:
    """Hash all published files so support-resource changes trigger an update."""
    digest = hashlib.sha256()
    ignored = {".DS_Store", "__pycache__"}
    for path in sorted(p for p in skill_dir.rglob("*") if p.is_file()):
        if any(part in ignored for part in path.parts):
            continue
        digest.update(path.relative_to(skill_dir).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _normalise_repo_url(value: str) -> str:
    return value.lower().removesuffix(".git").rstrip("/")


def trusted_git_revision(root: Path, expected_repo: str) -> Optional[str]:
    """Return HEAD only when the checkout really belongs to the configured repo."""
    try:
        remote = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if _normalise_repo_url(remote) != _normalise_repo_url(expected_repo):
            return None
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def fetch_catalog(source_key: str, source: dict, cache_root: Path) -> Path:
    """Clone or fast-forward a catalog in a crawler-owned cache."""
    repository = source["repository"]
    branch = source.get("branch", "main")
    sparse_paths = source.get("sparse_paths", [])
    destination = cache_root / source_key
    cache_root.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not (destination / ".git").is_dir():
        raise RuntimeError(f"refusing to replace non-git cache path: {destination}")
    if not destination.exists():
        command = ["git", "clone", "--depth", "1", "--branch", branch]
        if sparse_paths:
            command.extend(["--filter=blob:none", "--sparse"])
        command.extend([f"{repository}.git", str(destination)])
        subprocess.run(command, check=True)
        if sparse_paths:
            subprocess.run([
                "git", "-C", str(destination), "sparse-checkout", "set",
                *sparse_paths,
            ], check=True)
    else:
        actual = subprocess.run(
            ["git", "-C", str(destination), "remote", "get-url", "origin"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if _normalise_repo_url(actual) != _normalise_repo_url(repository):
            raise RuntimeError(f"cache remote mismatch for {source_key}: {actual}")
        if sparse_paths:
            subprocess.run([
                "git", "-C", str(destination), "sparse-checkout", "set",
                *sparse_paths,
            ], check=True)
        subprocess.run([
            "git", "-C", str(destination), "pull", "--ff-only", "origin", branch,
        ], check=True)
    return destination


def _load_optional_card(skill_dir: Path) -> str:
    card = skill_dir / "skill-card.md"
    return card.read_text(encoding="utf-8") if card.is_file() else ""


def build_skill_record(
    source_key: str,
    source: dict,
    root: Path,
    skill_name: str,
    revision: str,
    groups: Optional[list] = None,
) -> dict:
    relative_dir = Path(source.get("skills_path", "skills")) / skill_name
    skill_dir = root / relative_dir
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        raise ValueError(f"listed skill has no SKILL.md: {relative_dir}")
    content = skill_file.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(content)
    canonical_name = str(metadata["name"])
    if canonical_name != skill_name:
        raise ValueError(
            f"manifest/directory name {skill_name!r} differs from frontmatter {canonical_name!r}"
        )

    repository = source["repository"].rstrip("/")
    url_revision = revision if len(revision) == 40 else source.get("branch", "main")
    url = f"{repository}/tree/{url_revision}/{relative_dir.as_posix()}"
    tags = metadata.get("metadata", {}).get("tags", [])
    if not isinstance(tags, list):
        tags = []
    groups = groups or []
    all_tags = sorted(set(str(tag) for tag in [*tags, *groups]))
    directory_digest = content_digest(skill_dir)
    digest = hashlib.sha256(
        f"{directory_digest}:{json.dumps(sorted(groups))}".encode()
    ).hexdigest()
    unique_key = f"catalog:{source_key}:{canonical_name}"
    raw = {
        "catalog": source_key,
        "trust": source.get("trust", "community"),
        "groups": groups,
        "metadata": metadata,
        "skill_content": content,
        "skill_body": body,
        "skill_card": _load_optional_card(skill_dir),
        "content_hash": digest,
        "source_revision": revision,
    }
    return {
        "source": f"catalog:{source_key}",
        "source_key": unique_key,
        "source_repo": repository,
        "source_path": relative_dir.as_posix(),
        "source_revision": revision,
        "content_hash": digest,
        "name": canonical_name,
        "full_name": f"{source.get('author', source_key)}/{canonical_name}",
        "description": str(metadata["description"]),
        "url": url,
        "topics": all_tags,
        "decision": source.get("decision", "review"),
        "reason": (
            f"Discovered in the official {source_key} skill directory"
            if not groups else
            f"Selected from {source_key} official groups: {', '.join(groups)}"
        ),
        "confidence": source.get("confidence", 90),
        "site_status": "pending",
        "version": str(metadata.get("version", "")),
        "license": str(metadata.get("license", "")),
        "raw_data": raw,
    }


def sync_catalog(
    source_key: str,
    source: dict,
    db_path: Path,
    root: Optional[Path] = None,
    dry_run: bool = False,
) -> dict:
    started_at = utc_now()
    root = root or PROJECT_ROOT / source["local_path"]
    manifest_name = source.get("manifest")
    if manifest_name:
        manifest_path = root / manifest_name
        if not manifest_path.is_file():
            raise FileNotFoundError(f"catalog manifest not found: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        skills = selected_skill_groups(manifest, source.get("include_groups", []))
        revision_fallback = manifest_path.read_bytes()
    else:
        skills = discover_skill_directories(root, source.get("skills_path", "skills"))
        revision_fallback = "\n".join(sorted(skills)).encode()

    revision = trusted_git_revision(root, source["repository"])
    if not revision:
        revision = f"local-{hashlib.sha256(revision_fallback).hexdigest()[:12]}"

    records = [
        build_skill_record(source_key, source, root, name, revision, skills[name])
        for name in sorted(skills)
    ]
    stats = {
        "source": source_key,
        "started_at": started_at,
        "revision": revision,
        "discovered": len(records),
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "missing": 0,
        "status": "dry-run" if dry_run else "complete",
        "items": records if dry_run else [],
    }
    if dry_run:
        return stats

    active_keys = set()
    for record in records:
        active_keys.add(record["source_key"])
        result = insert_item("skill", record, db_path)
        stats[result] += 1
    stats["missing"] = mark_source_missing(
        "skill", f"catalog:{source_key}:", active_keys, db_path
    )
    record_source_sync(source_key, stats, db_path)
    return stats


def load_sources(path: Path = DEFAULT_CONFIG) -> Dict[str, dict]:
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return config.get("skill_catalogs", {})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="nvidia-skills")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "data" / "rosclaw_hub.db")
    parser.add_argument("--path", type=Path, help="Override the configured local catalog path")
    parser.add_argument("--fetch", action="store_true", help="Refresh a crawler-owned Git cache")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    sources = load_sources(args.config)
    if args.source not in sources:
        parser.error(f"unknown catalog source: {args.source}")
    source = sources[args.source]
    root = args.path
    if args.fetch:
        root = fetch_catalog(
            args.source, source, PROJECT_ROOT / "data" / "source_cache"
        )
    elif root is None:
        root = PROJECT_ROOT / source["local_path"]

    try:
        stats = sync_catalog(args.source, source, args.db, root, args.dry_run)
    except Exception as exc:
        print(f"catalog sync failed: {exc}", file=sys.stderr)
        return 1
    output = stats if args.json else {k: v for k, v in stats.items() if k != "items"}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
