"""ROSClaw Ecology Crawler - Phase 1: Awesome Lists Extractor"""

import re
import time
from typing import List, Optional, Dict

import requests
from sqlalchemy.orm import Session

from config import (
    AWESOME_LIST_URLS,
    AGENT_SKILL_AWESOME_URLS,
    MCP_AWESOME_URLS,
)
from database import RosclawHubResource
from utils import (
    classify_embodied,
    extract_repo_owner_name,
    normalize_github_url,
    guess_resource_type,
)


def infer_type_from_awesome_source(list_url: str) -> str:
    """Force type based on which awesome list the repo came from."""
    norm_list = normalize_github_url(list_url)
    for url in AGENT_SKILL_AWESOME_URLS:
        if normalize_github_url(url) == norm_list:
            return "agent_skill"
    for url in MCP_AWESOME_URLS:
        if normalize_github_url(url) == norm_list:
            return "mcp_server"
    return ""


GITHUB_MIRRORS = [
    ("https://ghfast.top/https://raw.githubusercontent.com", 30),
    ("https://raw.githubusercontent.com", 8),
]


def fetch_raw_readme(owner: str, repo: str) -> Optional[str]:
    """Fetch README.md with mirror fallback (main -> master fallback)."""
    for branch in ("main", "master"):
        for mirror, timeout_sec in GITHUB_MIRRORS:
            url = f"{mirror}/{owner}/{repo}/{branch}/README.md"
            try:
                resp = requests.get(url, timeout=timeout_sec)
                if resp.status_code == 200:
                    print(f"[FETCHED] {url}")
                    return resp.text
            except Exception as e:
                print(f"[WARN] Failed fetching {url}: {e}")
    return None


def extract_github_links_with_context(markdown_text: str) -> List[Dict[str, str]]:
    """
    Parse markdown text and extract GitHub repo URLs along with nearby
    descriptive text (same line or the line immediately following a header).
    Returns a list of dicts: {"repo_url": str, "name": str, "description": str}
    """
    results = []
    seen = set()

    lines = markdown_text.splitlines()
    for idx, line in enumerate(lines):
        # Find all github links in this line
        matches = re.findall(
            r"https?://(?:www\.)?github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:/[^\s\)\]\"]*)?",
            line,
        )
        for match in matches:
            norm = normalize_github_url(match)
            if norm in seen:
                continue
            seen.add(norm)

            owner, repo_name = extract_repo_owner_name(norm)
            if not owner or not repo_name:
                continue

            # Derive description from current line (remove the URL and bullet syntax)
            desc = line.replace(match, "").strip()
            desc = re.sub(r"^[-*+]\s*", "", desc)  # remove markdown bullet
            desc = re.sub(r"^\[.*?\]\s*", "", desc)  # remove badges/tags like [ MCP ]
            desc = re.sub(r"^[-–—:]\s*", "", desc)  # remove leading separators
            desc = desc.strip()

            # If current line is mostly empty, look at previous line (header/title)
            if not desc and idx > 0:
                prev = lines[idx - 1].strip()
                # Remove header markdown
                prev = re.sub(r"^#+\s*", "", prev)
                desc = prev

            results.append(
                {
                    "repo_url": norm,
                    "name": repo_name,
                    "description": desc or repo_name,
                }
            )
    return results


def run_phase_1(session: Session) -> int:
    """
    Phase 1 main runner.
    Scrapes the configured Awesome Lists, extracts GitHub repo links,
    classifies them, deduplicates against the DB, and inserts/updates records.
    Returns the number of new records inserted.
    """
    inserted_count = 0

    print("=" * 60)
    print("PHASE 1: Awesome Lists Extractor (Firecrawl fallback to Raw GitHub)")
    print("=" * 60)

    for list_url in AWESOME_LIST_URLS:
        print(f"\n[PROCESSING] {list_url}")
        owner, repo = extract_repo_owner_name(list_url)
        if not owner or not repo:
            print(f"[SKIP] Cannot parse owner/repo from {list_url}")
            continue

        readme = fetch_raw_readme(owner, repo)
        if not readme:
            print(f"[SKIP] Could not fetch README for {owner}/{repo}")
            continue

        print(f"[FETCHED] README length: {len(readme)} chars")

        items = extract_github_links_with_context(readme)
        print(f"[EXTRACTED] {len(items)} unique GitHub links")

        for item in items:
            repo_url = item["repo_url"]

            # Skip the awesome list itself
            if normalize_github_url(list_url) == repo_url:
                continue

            # Check DB for existing record
            existing = (
                session.query(RosclawHubResource)
                .filter_by(repo_url=repo_url)
                .first()
            )

            is_embodied, matched_tags = classify_embodied(
                f"{item['name']} {item['description']}"
            )
            forced_type = infer_type_from_awesome_source(list_url)
            if forced_type:
                resource_type = forced_type
            else:
                resource_type = guess_resource_type(
                    item["name"], item["description"], source="awesome_list"
                )

            if existing:
                # Update source tag and correct type if forced by awesome list origin
                sources = set((existing.source or "").split(","))
                sources.add("awesome_list")
                existing.source = ",".join(s for s in sorted(sources) if s)
                if forced_type and existing.type != forced_type:
                    existing.type = forced_type
                if is_embodied:
                    existing.is_embodied = True
                    existing.domain_tags = list(
                        set((existing.domain_tags or []) + matched_tags)
                    )
                with session.no_autoflush:
                    session.merge(existing)
            else:
                record = RosclawHubResource(
                    type=resource_type,
                    source="awesome_list",
                    repo_url=repo_url,
                    name=item["name"],
                    description=item["description"],
                    domain_tags=matched_tags if matched_tags else [],
                    stars=0,
                    is_embodied=is_embodied,
                )
                session.add(record)
                inserted_count += 1

            if inserted_count % 50 == 0:
                session.commit()

        # Small polite delay
        time.sleep(0.5)
    
    session.commit()
    
    # Check for potential duplicates
    from sqlalchemy import func as sql_func
    duplicates = session.query(
        RosclawHubResource.repo_url,
        sql_func.count(RosclawHubResource.id).label('count')
    ).group_by(RosclawHubResource.repo_url).having(sql_func.count(RosclawHubResource.id) > 1).all()
    
    if duplicates:
        print(f"\n⚠️  Found {len(duplicates)} repo_urls with multiple records:")
        for repo_url, count in duplicates[:5]:
            print(f"  - {repo_url}: {count} records")
    else:
        print("\n✅ All repo_urls are unique")
    
    print(f"\n[PHASE 1 COMPLETE] New records inserted: {inserted_count}")
    return inserted_count


if __name__ == "__main__":
    # Quick standalone test
    from database import init_db, get_session

    engine = init_db("rosclaw_hub.db")
    db_session = get_session(engine)
    run_phase_1(db_session)
    db_session.close()
