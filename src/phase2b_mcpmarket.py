"""ROSClaw Ecology Crawler - Phase 2B: Deep Scrape MCP Market"""

import json
import re
import subprocess
import time
from typing import List, Dict, Optional

from curl_cffi import requests
from sqlalchemy.orm import Session

from config import MCPMARKET_LIST_PAGES, CURL_PROXIES
from database import RosclawHubResource
from utils import (
    classify_embodied,
    extract_repo_owner_name,
    normalize_github_url,
)


def firecrawl_scrape(url: str) -> Optional[Dict]:
    """Use local Firecrawl CLI to scrape a JS-rendered page."""
    try:
        cmd = [
            "/home/ubuntu/.npm-global/bin/firecrawl", "scrape", url,
            "-f", "markdown,links",
            "--json", "--pretty",
            "-o", "/tmp/mcpmarket_firecrawl.json",
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        with open("/tmp/mcpmarket_firecrawl.json", "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Firecrawl failed for {url}: {e}")
        return None


_SKIP_SLUGS = {"leaderboard", "categories", "search"}


def extract_mcpmarket_links(firecrawl_result: Dict) -> List[Dict[str, str]]:
    """Extract server/skill links from Firecrawl JSON result."""
    links = firecrawl_result.get("links", [])
    results = []
    seen = set()
    for link in links:
        if "/zh/server/" in link:
            slug = link.split("/zh/server/")[-1].split("?")[0].split("#")[0]
            if slug and slug not in seen and slug not in _SKIP_SLUGS:
                seen.add(slug)
                results.append({"type": "mcp_server", "slug": slug, "url": link})
        elif "/zh/tools/skills/" in link:
            slug = link.split("/zh/tools/skills/")[-1].split("?")[0].split("#")[0]
            if slug and slug not in seen and slug not in _SKIP_SLUGS:
                seen.add(slug)
                results.append({"type": "agent_skill", "slug": slug, "url": link})
        # FIX: also capture daily snapshot archive pages
        elif "/zh/daily/skills/top-skill-list-" in link:
            slug = link.split("/zh/daily/skills/")[-1].split("?")[0].split("#")[0]
            if slug and slug not in seen:
                seen.add(slug)
                results.append({"type": "agent_skill", "slug": slug, "url": link, "is_archive": True})
        elif "/zh/daily/top-server-list-" in link:
            slug = link.split("/zh/daily/")[-1].split("?")[0].split("#")[0]
            if slug and slug not in seen:
                seen.add(slug)
                results.append({"type": "mcp_server", "slug": slug, "url": link, "is_archive": True})
    return results


def fetch_github_from_mcpmarket_detail(url: str) -> Optional[str]:
    """Use curl_cffi to hit a mcpmarket detail page and extract the main GitHub repo URL."""
    try:
        resp = requests.get(
            url, impersonate="chrome120",
            proxies=CURL_PROXIES, timeout=20,
        )
        if resp.status_code != 200:
            return None
        html = resp.text
        matches = re.findall(
            r"https?://(?:www\.)?github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+",
            html,
        )
        if not matches:
            return None
        BLACKLISTED_PATHS = {
            "username/skill-repo",
            "username/mcp-server",
        }
        for m in matches:
            if "/sponsors/" in m or "/issues" in m or "/blob/" in m:
                continue
            norm = normalize_github_url(m)
            parsed_path = norm.replace("https://github.com/", "")
            if parsed_path in BLACKLISTED_PATHS:
                continue
            return norm
        return normalize_github_url(matches[0])
    except Exception as e:
        print(f"[WARN] curl_cffi failed for {url}: {e}")
        return None


def _extract_archive_items(firecrawl_result: Dict, archive_type: str) -> List[Dict[str, str]]:
    """From an archive page markdown, extract individual server/skill detail links."""
    links = firecrawl_result.get("links", [])
    results = []
    seen = set()
    for link in links:
        if archive_type == "agent_skill" and "/zh/tools/skills/" in link and "top-skill-list-" not in link:
            slug = link.split("/zh/tools/skills/")[-1].split("?")[0].split("#")[0]
            if slug and slug not in seen:
                seen.add(slug)
                results.append({"type": "agent_skill", "slug": slug, "url": link})
        elif archive_type == "mcp_server" and "/zh/server/" in link and "top-server-list-" not in link:
            slug = link.split("/zh/server/")[-1].split("?")[0].split("#")[0]
            if slug and slug not in seen:
                seen.add(slug)
                results.append({"type": "mcp_server", "slug": slug, "url": link})
    return results


def run_phase_2b(session: Session, max_pages: int = 0) -> int:
    """
    Deep-scrape MCP Market leaderboards.
    max_pages=0 means scrape all discovered detail pages.
    """
    inserted_count = 0
    print("\n" + "=" * 60)
    print("PHASE 2B: MCP Market Deep Scraper (Firecrawl + curl_cffi)")
    print("=" * 60)

    all_items: List[Dict[str, str]] = []
    for list_page in MCPMARKET_LIST_PAGES:
        print(f"\n[FIRECRAWL] {list_page}")
        result = firecrawl_scrape(list_page)
        if not result:
            continue
        items = extract_mcpmarket_links(result)
        print(f"[EXTRACTED] {len(items)} server/skill links")
        all_items.extend(items)
        time.sleep(2)

    if not all_items:
        print("[SKIP] No MCP Market detail pages found")
        return 0

    # Expand archive pages to individual detail pages
    expanded_items: List[Dict[str, str]] = []
    for item in all_items:
        if item.get("is_archive"):
            print(f"[ARCHIVE] Expanding {item['url']}")
            result = firecrawl_scrape(item["url"])
            if result:
                sub_items = _extract_archive_items(result, item["type"])
                print(f"  -> {len(sub_items)} items")
                expanded_items.extend(sub_items)
                time.sleep(2)
            continue
        expanded_items.append(item)

    print(f"\n[TOTAL DETAIL PAGES] {len(expanded_items)}")
    if max_pages > 0:
        expanded_items = expanded_items[:max_pages]

    processed_since_commit = 0
    for idx, item in enumerate(expanded_items, 1):
        url = item["url"]
        expected_type = item["type"]
        print(f"[{idx}/{len(expanded_items)}] {url}")

        repo_url = fetch_github_from_mcpmarket_detail(url)
        if not repo_url:
            print("  -> No GitHub link found")
            continue

        existing = (
            session.query(RosclawHubResource)
            .filter_by(repo_url=repo_url)
            .first()
        )

        owner, repo_name = extract_repo_owner_name(repo_url)
        if not owner or not repo_name:
            continue

        desc = f"Found on MCP Market: {item['slug'].replace('-', ' ')}"
        is_embodied, matched_tags = classify_embodied(f"{repo_name} {desc}")

        if existing:
            sources = set((existing.source or "").split(","))
            sources.add("mcpmarket")
            existing.source = ",".join(s for s in sorted(sources) if s)
            if is_embodied:
                existing.is_embodied = True
                existing.domain_tags = list(
                    set((existing.domain_tags or []) + matched_tags)
                )
            if existing.type != expected_type:
                existing.type = expected_type
            session.merge(existing)
            print("  -> Existing repo updated")
        else:
            record = RosclawHubResource(
                type=expected_type,
                source="mcpmarket",
                repo_url=repo_url,
                name=repo_name,
                description=desc,
                domain_tags=matched_tags if matched_tags else [],
                stars=0,
                is_embodied=is_embodied,
            )
            session.add(record)
            inserted_count += 1
            print("  -> New record inserted")

        processed_since_commit += 1
        if processed_since_commit >= 50:
            try:
                session.commit()
                print(f"  -> COMMITTED (progress {idx})")
            except Exception as e:
                print(f"  -> COMMIT ERROR: {e}")
                session.rollback()
            processed_since_commit = 0

        time.sleep(0.8)

    try:
        session.commit()
    except Exception as e:
        print(f"[FINAL COMMIT ERROR] {e}")
        session.rollback()
    print(f"\n[PHASE 2B COMPLETE] New records inserted: {inserted_count}")
    return inserted_count


if __name__ == "__main__":
    from database import init_db, get_session
    engine = init_db("rosclaw_hub.db")
    db_session = get_session(engine)
    run_phase_2b(db_session)
    db_session.close()
