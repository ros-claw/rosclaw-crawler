#!/usr/bin/env python3
"""Stage broad GitHub MCP and Agent Skill discoveries for human/LLM review."""

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.client import IncompleteRead
from pathlib import Path

import yaml

from catalog_sync import parse_frontmatter
from database import connect, insert_item, record_source_sync, utc_now
from reporting import write_json_report


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
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise
            except (urllib.error.URLError, TimeoutError, ConnectionError, IncompleteRead):
                if attempt == 2:
                    raise
            time.sleep(2 ** attempt)

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
        return [], [], [], None
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
        "value": {**state, "mcp_index": next_mcp, "skill_index": next_skill},
    }
    return (
        [f'"mcp server" "{term}"' for term in mcp_terms],
        [f'filename:SKILL.md "{term}"' for term in skill_terms],
        [f'skills "{term}" in:name,description,readme' for term in skill_terms],
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
    # Git blob SHAs identify immutable content. Reuse locally stored evidence
    # when search/tree results still point at the same blob.
    cache = getattr(client, "skill_content_cache", {})
    content = cache.get(result.get("sha"))
    if content is None:
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
        "url": (
            repo["html_url"] if skill_dir == "." else
            html_url.rsplit("/", 1)[0].replace("/blob/", "/tree/", 1)
        ),
        "topics": ["github-discovery", "physical-ai"],
        "decision": "review",
        "reason": f"Matched GitHub Agent Skill discovery query: {query}",
        "confidence": 65,
        "site_status": "pending",
        "version": str(metadata.get("version", "")),
        "license": str(metadata.get("license", "")),
        "raw_data": {"metadata": metadata, "skill_content": content, "github": result},
    }


def skill_results_from_repository(
    client: GitHubClient,
    repo: dict,
    max_skills: int = 25,
    offset: int = 0,
) -> list:
    """Enumerate SKILL.md blobs without waiting for GitHub Code Search indexing."""
    full_name = repo["full_name"]
    branch = repo.get("default_branch") or "main"
    tree = client.get(f"/repos/{full_name}/git/trees/{branch}", {"recursive": 1})
    if tree.get("truncated"):
        raise ValueError(f"GitHub tree truncated for {full_name}; incomplete enumeration")
    results = []
    for item in sorted(tree.get("tree", []), key=lambda value: value.get("path", "")):
        path = item.get("path", "")
        if item.get("type") != "blob" or Path(path).name.lower() != "skill.md":
            continue
        results.append({
            "url": item["url"],
            "path": path,
            "sha": item.get("sha", ""),
            "html_url": f"{repo['html_url']}/blob/{branch}/{path}",
            "repository": repo,
        })
    if not results:
        return results
    offset %= len(results)
    rotated = results[offset:] + results[:offset]
    return rotated[:max_skills]


def discover(config: dict, client: GitHubClient, errors: list = None) -> tuple:
    errors = errors if errors is not None else []

    def attempt(label, operation, fallback=None):
        try:
            return operation()
        except Exception as exc:
            errors.append({"operation": label, "error": str(exc)})
            return fallback

    limit = config.get("max_results_per_query", 20)
    records = {}
    taxonomy_mcp, taxonomy_skill, taxonomy_skill_repos, next_state = (
        taxonomy_queries(config)
    )
    mcp_queries = list(dict.fromkeys([*config.get("mcp", []), *taxonomy_mcp]))
    skill_queries = list(dict.fromkeys([*config.get("skill", []), *taxonomy_skill]))
    skill_repository_queries = list(dict.fromkeys([
        *config.get("skill_repositories", []), *taxonomy_skill_repos,
    ]))
    for query in mcp_queries:
        for repo in attempt(f"mcp search: {query}",
                            lambda: client.search("repositories", query, limit), []):
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
        for result in attempt(f"skill search: {query}",
                              lambda: client.search("code", query, limit), []):
            skill_results[result["url"]] = (result, query)
    skill_repositories = {}
    for query in skill_repository_queries:
        for repo in attempt(f"skill repository search: {query}",
                            lambda: client.search("repositories", query, limit), []):
            searchable = " ".join([
                repo.get("full_name", ""), repo.get("description") or "", query,
            ])
            if is_physical(searchable):
                skill_repositories[repo["full_name"].lower()] = (repo, query)
    repository_limit = config.get("max_skill_repositories_per_run", 12)
    max_skills = config.get("max_skills_per_repository", 25)
    rotation = next_state["value"] if next_state else {}
    offsets = rotation.setdefault("skill_offsets", {})
    repositories = list(skill_repositories.values())
    if repositories:
        start = rotation.get("repository_index", 0) % len(repositories)
        repositories = repositories[start:] + repositories[:start]
        rotation["repository_index"] = start + repository_limit

    def enumerate_repo(repo):
        name = repo["full_name"].lower()
        results = attempt(f"skill tree: {name}", lambda: skill_results_from_repository(
            client, repo, max_skills, offsets.get(name, 0)), [])
        offsets[name] = offsets.get(name, 0) + len(results)
        return results

    for repo, query in repositories[:repository_limit]:
        for result in enumerate_repo(repo):
            skill_results[result["url"]] = (result, query)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(skill_record, client, result, query): result["url"]
            for result, query in skill_results.values()
        }
        for future in as_completed(futures):
            record = attempt(f"skill content: {futures[future]}", future.result)
            if record:
                records[record["source_key"]] = ("skill", record)

    for full_name in config.get("seed_repositories", {}).get("mcp", []):
        repo = attempt(f"mcp seed: {full_name}", lambda: client.get(f"/repos/{full_name}"))
        if repo is None:
            continue
        record = mcp_record(repo, "targeted physical-AI seed")
        records[record["source_key"]] = ("mcp", record)
    for seed in config.get("seed_repositories", {}).get("skill", []):
        full_name, path = seed["repository"], seed.get("path")
        repo = attempt(f"skill seed: {full_name}", lambda: client.get(f"/repos/{full_name}"))
        if repo is None:
            continue
        if path:
            seeded = attempt(f"skill seed content: {full_name}/{path}",
                             lambda: client.get(f"/repos/{full_name}/contents/{path}"))
            if seeded is None:
                continue
            seeded_results = [seeded]
            seeded_results[0]["repository"] = repo
        else:
            seeded_results = enumerate_repo(repo)
        for result in seeded_results:
            record = attempt(f"skill seed parse: {full_name}/{result['path']}",
                             lambda: skill_record(client, result, "targeted physical-AI seed"))
            if record:
                records[record["source_key"]] = ("skill", record)
    return list(records.values()), next_state


def sync_github(config: dict, client: GitHubClient, db_path: Path, dry_run=False) -> dict:
    started_at = utc_now()
    client.skill_content_cache = {}
    if db_path.exists():
        conn = connect(db_path)
        try:
            for row in conn.execute("SELECT raw_data FROM skills WHERE source='github-discovery'"):
                raw = json.loads(row["raw_data"] or "{}")
                sha = raw.get("github", {}).get("sha")
                content = raw.get("skill_content")
                if sha and content:
                    client.skill_content_cache[sha] = content
        finally:
            conn.close()
    errors = []
    records, next_state = discover(config, client, errors)
    stats = {
        "source": "github-discovery", "started_at": started_at,
        "revision": utc_now(), "discovered": len(records), "created": 0,
        "updated": 0, "unchanged": 0, "missing": 0,
        "status": "dry-run" if dry_run else ("partial" if errors else "complete"),
        "details": {"operation_errors": errors,
                    "cached_skill_blobs": len(client.skill_content_cache)},
        "items": [record for _, record in records] if dry_run else [],
    }
    if dry_run:
        return stats
    for item_type, record in records:
        stats[insert_item(item_type, record, db_path)] += 1
    # Search is always a bounded sample, even without taxonomy rotation.
    # Absence from search results cannot establish an upstream deletion.
    record_source_sync("github-discovery", stats, db_path)
    if next_state:
        write_json_report(next_state["path"], next_state["value"])
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
