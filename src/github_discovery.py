#!/usr/bin/env python3
"""Stage broad GitHub MCP and Agent Skill discoveries for human/LLM review."""

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

from catalog_sync import parse_frontmatter
from database import insert_item, mark_source_missing, record_source_sync, utc_now


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "sources.yaml"
API = "https://api.github.com"
PHYSICAL_TERMS = (
    "robot", "robotics", " ros ", "ros2", "physical ai", "embodied ai",
    "drone", "uav", "mavlink", "px4", "manipulator", "gripper",
    "actuator", "sensor", "plc", "industrial automation", "isaac sim",
    "gazebo", "mujoco", "autonomous vehicle", "3d print", "cnc",
)


class GitHubClient:
    def __init__(self, token: str):
        if not token:
            raise ValueError("GITHUB_TOKEN is required for GitHub code discovery")
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "rosclaw-crawler/3.0",
        }

    def get(self, path_or_url: str, params=None) -> dict:
        url = path_or_url if path_or_url.startswith("http") else f"{API}{path_or_url}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        parsed = urllib.parse.urlsplit(url)
        url = urllib.parse.urlunsplit((
            parsed.scheme, parsed.netloc,
            urllib.parse.quote(urllib.parse.unquote(parsed.path), safe="/:%@"),
            parsed.query, parsed.fragment,
        ))
        request = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def search(self, kind: str, query: str, per_page: int) -> list:
        params = {"q": query, "per_page": per_page}
        if kind == "repositories":
            params.update({"sort": "updated", "order": "desc"})
        return self.get(f"/search/{kind}", params).get("items", [])

    def content(self, api_url: str) -> str:
        data = self.get(api_url)
        return base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")


def is_physical(text: str) -> bool:
    haystack = f" {text.lower()} "
    terms = list(PHYSICAL_TERMS)
    taxonomy_path = PROJECT_ROOT / "physical_ai_taxonomy.yaml"
    if taxonomy_path.is_file():
        taxonomy = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8")) or {}
        terms.extend(taxonomy.get("physical_anchors", []))
    for term in terms:
        term = term.lower()
        if " " not in term and term.replace("-", "").isalnum():
            if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", haystack):
                return True
        elif term in haystack:
            return True
    return False


def taxonomy_queries(config: dict) -> tuple:
    taxonomy_path = PROJECT_ROOT / config.get("taxonomy", "physical_ai_taxonomy.yaml")
    if not taxonomy_path.is_file():
        return [], [], None
    taxonomy = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8")) or {}
    terms = []
    for category in taxonomy.get("categories", {}).values():
        terms.extend(category.get("search_terms", []))
    terms = list(dict.fromkeys(terms))
    state_path = PROJECT_ROOT / config.get(
        "rotation_state_file", "data/github_taxonomy_rotation.json"
    )
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        state = {"mcp_index": 0, "skill_index": 0}

    def take(index, count):
        if not terms:
            return [], 0
        selected = [terms[(index + offset) % len(terms)] for offset in range(count)]
        return selected, (index + count) % len(terms)

    mcp_terms, next_mcp = take(
        state.get("mcp_index", 0), config.get("taxonomy_mcp_terms_per_run", 12)
    )
    skill_terms, next_skill = take(
        state.get("skill_index", 0), config.get("taxonomy_skill_terms_per_run", 6)
    )
    next_state = {
        "path": state_path,
        "value": {"mcp_index": next_mcp, "skill_index": next_skill},
    }
    return (
        [f'"mcp server" "{term}"' for term in mcp_terms],
        [f'filename:SKILL.md "{term}"' for term in skill_terms],
        next_state,
    )


def mcp_record(repo: dict, query: str) -> dict:
    full_name = repo["full_name"]
    identity = f"{repo.get('pushed_at', '')}:{repo.get('description', '')}"
    return {
        "source": "github-discovery",
        "source_key": f"github:mcp:{full_name.lower()}",
        "source_repo": repo["html_url"],
        "source_revision": repo.get("pushed_at", ""),
        "content_hash": hashlib.sha256(identity.encode()).hexdigest(),
        "name": repo["name"],
        "full_name": full_name,
        "description": repo.get("description") or "",
        "url": repo["html_url"],
        "stars": repo.get("stargazers_count", 0),
        "language": repo.get("language") or "",
        "topics": repo.get("topics", []) + ["github-discovery"],
        "decision": "review",
        "reason": f"Matched GitHub MCP discovery query: {query}",
        "confidence": 55,
        "site_status": "pending",
        "upstream_updated_at": repo.get("pushed_at"),
        "raw_data": repo,
    }


def skill_record(client: GitHubClient, result: dict, query: str):
    content = client.content(result["url"])
    try:
        metadata, _ = parse_frontmatter(content)
    except ValueError:
        return None
    if not is_physical(f"{metadata.get('name', '')} {metadata.get('description', '')} {content[:5000]}"):
        return None
    repo = result["repository"]
    path = result["path"]
    skill_dir = str(Path(path).parent)
    canonical_name = str(metadata["name"])
    source_key = f"github:skill:{repo['full_name'].lower()}:{skill_dir.lower()}"
    digest = hashlib.sha256(content.encode()).hexdigest()
    html_url = result.get("html_url") or f"{repo['html_url']}/blob/{repo['default_branch']}/{path}"
    return {
        "source": "github-discovery",
        "source_key": source_key,
        "source_repo": repo["html_url"],
        "source_path": skill_dir,
        "source_revision": result.get("sha", ""),
        "content_hash": digest,
        "name": canonical_name,
        "full_name": f"{repo['owner']['login']}/{canonical_name}",
        "description": str(metadata["description"]),
        "url": html_url.rsplit("/SKILL.md", 1)[0],
        "topics": ["github-discovery", "physical-ai"],
        "decision": "review",
        "reason": f"Matched GitHub Agent Skill discovery query: {query}",
        "confidence": 65,
        "site_status": "pending",
        "version": str(metadata.get("version", "")),
        "license": str(metadata.get("license", "")),
        "raw_data": {"metadata": metadata, "skill_content": content, "github": result},
    }


def discover(config: dict, client: GitHubClient) -> tuple:
    limit = config.get("max_results_per_query", 20)
    records = {}
    taxonomy_mcp, taxonomy_skill, next_state = taxonomy_queries(config)
    mcp_queries = list(dict.fromkeys([*config.get("mcp", []), *taxonomy_mcp]))
    skill_queries = list(dict.fromkeys([*config.get("skill", []), *taxonomy_skill]))
    for query in mcp_queries:
        for repo in client.search("repositories", query, limit):
            searchable = " ".join([
                repo.get("full_name", ""),
                repo.get("description") or "",
                " ".join(repo.get("topics", [])),
            ])
            if not is_physical(searchable):
                continue
            record = mcp_record(repo, query)
            records[record["source_key"]] = ("mcp", record)
    skill_results = {}
    for query in skill_queries:
        for result in client.search("code", query, limit):
            skill_results[result["url"]] = (result, query)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(skill_record, client, result, query): result["url"]
            for result, query in skill_results.values()
        }
        for future in as_completed(futures):
            record = future.result()
            if record:
                records[record["source_key"]] = ("skill", record)

    for full_name in config.get("seed_repositories", {}).get("mcp", []):
        repo = client.get(f"/repos/{full_name}")
        record = mcp_record(repo, "targeted physical-AI seed")
        records[record["source_key"]] = ("mcp", record)
    for seed in config.get("seed_repositories", {}).get("skill", []):
        full_name, path = seed["repository"], seed.get("path", "SKILL.md")
        repo = client.get(f"/repos/{full_name}")
        result = client.get(f"/repos/{full_name}/contents/{path}")
        result["repository"] = repo
        record = skill_record(client, result, "targeted physical-AI seed")
        if record:
            records[record["source_key"]] = ("skill", record)
    return list(records.values()), next_state


def sync_github(config: dict, client: GitHubClient, db_path: Path, dry_run=False) -> dict:
    started_at = utc_now()
    records, next_state = discover(config, client)
    stats = {
        "source": "github-discovery", "started_at": started_at,
        "revision": utc_now(), "discovered": len(records), "created": 0,
        "updated": 0, "unchanged": 0, "missing": 0,
        "status": "dry-run" if dry_run else "complete",
        "items": [record for _, record in records] if dry_run else [],
    }
    if dry_run:
        return stats
    for item_type, record in records:
        stats[insert_item(item_type, record, db_path)] += 1
    mcp_keys = {record["source_key"] for kind, record in records if kind == "mcp"}
    skill_keys = {record["source_key"] for kind, record in records if kind == "skill"}
    # Taxonomy queries rotate across runs, so absence from one partial slice is
    # not evidence that a GitHub item disappeared upstream.
    if not config.get("taxonomy"):
        stats["missing"] += mark_source_missing(
            "mcp", "github:mcp:", mcp_keys, db_path
        )
        stats["missing"] += mark_source_missing(
            "skill", "github:skill:", skill_keys, db_path
        )
    record_source_sync("github-discovery", stats, db_path)
    if next_state:
        next_state["path"].parent.mkdir(parents=True, exist_ok=True)
        next_state["path"].write_text(
            json.dumps(next_state["value"], indent=2) + "\n", encoding="utf-8"
        )
    return stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "data" / "rosclaw_hub.db")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    try:
        client = GitHubClient(os.getenv("GITHUB_TOKEN", ""))
        stats = sync_github(config.get("github_discovery", {}), client, args.db, args.dry_run)
    except Exception as exc:
        print(f"GitHub discovery failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({k: v for k, v in stats.items() if k != "items"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
