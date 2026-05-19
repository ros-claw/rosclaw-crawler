"""ROSClaw Ecology Crawler - Phase 2: Hub Directory Scraper (Enhanced with Deep Scraping)"""

import json
import re
import subprocess
import time
from typing import List, Dict, Optional

from curl_cffi import requests
from sqlalchemy.orm import Session

from config import HUB_DIRECTORY_URLS, CURL_PROXIES
from database import RosclawHubResource
from utils import (
    classify_embodied,
    extract_repo_owner_name,
    normalize_github_url,
    guess_resource_type,
)


def firecrawl_scrape(url: str) -> Optional[Dict]:
    """Use local Firecrawl CLI to scrape a JS-rendered page."""
    try:
        out_path = f"/tmp/hub_firecrawl_{re.sub(r'[^a-zA-Z0-9]', '_', url)}.json"
        cmd = [
            "/home/ubuntu/.npm-global/bin/firecrawl", "scrape", url,
            "-f", "markdown,links",
            "--json", "--pretty",
            "-o", out_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        with open(out_path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Firecrawl failed for {url}: {e}")
        return None


def fetch_github_from_url(url: str) -> Optional[str]:
    """Use curl_cffi to fetch a page and extract the first valid GitHub repo URL."""
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
        BLACKLISTED_PATHS = {
            "settings", "docs", "blob", "tree", "issues", "pulls", "actions",
            "security", "insights", "releases", "tags", "license",
        }
        for m in matches:
            if any(f"/{bp}/" in m.lower() for bp in BLACKLISTED_PATHS):
                continue
            if "/sponsors/" in m:
                continue
            norm = normalize_github_url(m)
            # Validate it looks like owner/repo
            parts = norm.replace("https://github.com/", "").split("/")
            if len(parts) >= 2 and len(parts[0]) > 0 and len(parts[1]) > 0:
                return norm
        return None
    except Exception as e:
        print(f"[WARN] curl_cffi failed for {url}: {e}")
        return None


def extract_detail_links(firecrawl_result: Dict, url: str) -> List[Dict[str, str]]:
    """Extract detail page links from hub listing pages."""
    results = []
    seen = set()
    links = firecrawl_result.get("links", [])
    
    if "skills.sh" in url:
        # Pattern: https://skills.sh/owner/repo/skill-name
        for link in links:
            m = re.match(r"https://skills\.sh/([^/]+)/([^/]+)/([^/]+)", link)
            if m:
                key = f"{m.group(1)}/{m.group(2)}"
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "detail_url": link,
                        "expected_type": "agent_skill",
                        "name_hint": m.group(3),
                    })
    
    elif "mcpservers.org" in url:
        # Pattern: https://mcpservers.org/servers/...
        for link in links:
            if "/servers/" in link and "mcpservers.org" in link:
                slug = link.split("/servers/")[-1].split("?")[0].split("#")[0]
                if slug and slug not in seen:
                    seen.add(slug)
                    expected_type = "agent_skill" if "agent-skills" in url else "mcp_server"
                    results.append({
                        "detail_url": link,
                        "expected_type": expected_type,
                        "name_hint": slug.split("/")[-1] if "/" in slug else slug,
                    })
    
    return results


def extract_github_links_direct(firecrawl_result: Dict) -> List[Dict[str, str]]:
    """Extract direct GitHub repo URLs from Firecrawl result."""
    results = []
    seen = set()
    links = firecrawl_result.get("links", [])
    markdown = firecrawl_result.get("markdown", "")

    for source_text in links + [markdown]:
        matches = re.finditer(
            r"https?://(?:www\.)?github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:/[^\s\"'\)>]*)?",
            source_text,
        )
        for m in matches:
            raw_url = m.group(0)
            norm = normalize_github_url(raw_url)
            if not norm or norm in seen:
                continue
            seen.add(norm)

            owner, repo_name = extract_repo_owner_name(norm)
            if not owner or not repo_name:
                continue

            # Try to extract nearby description from markdown
            start = max(m.start() - 400, 0)
            end = min(m.end() + 400, len(markdown))
            snippet = markdown[start:end]
            text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", snippet)
            text = re.sub(r"[#*_`\-|]+", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            desc = text[:300] if len(text) > 300 else text
            if not desc:
                desc = repo_name

            results.append({
                "repo_url": norm,
                "name": repo_name,
                "description": desc,
            })
    return results


def run_phase_2(session: Session) -> int:
    inserted_count = 0

    print("\n" + "=" * 60)
    print("PHASE 2: Hub Directory Scraper (Firecrawl + Deep Scraping)")
    print("=" * 60)

    for url in HUB_DIRECTORY_URLS:
        print(f"\n[PROCESSING] {url}")
        result = firecrawl_scrape(url)
        if not result:
            print(f"[SKIP] Could not scrape {url}")
            continue

        # First, try direct GitHub link extraction (works for some hubs)
        direct_items = extract_github_links_direct(result)
        print(f"[DIRECT] {len(direct_items)} unique GitHub links")

        for item in direct_items:
            repo_url = item["repo_url"]
            existing = session.query(RosclawHubResource).filter_by(repo_url=repo_url).first()

            is_embodied, matched_tags = classify_embodied(f"{item['name']} {item['description']}")

            if "lobehub.com/zh/skills" in url or "mcpservers.org/agent-skills" in url:
                resource_type = "agent_skill"
            elif "lobehub.com/zh/mcp" in url or "mcpservers.org/" in url:
                resource_type = "mcp_server"
            else:
                resource_type = guess_resource_type(item["name"], item["description"], source="hub_directory")

            if existing:
                sources = set((existing.source or "").split(","))
                sources.add("hub_directory")
                existing.source = ",".join(s for s in sorted(sources) if s)
                if is_embodied:
                    existing.is_embodied = True
                    existing.domain_tags = list(set((existing.domain_tags or []) + matched_tags))
                session.merge(existing)
            else:
                record = RosclawHubResource(
                    type=resource_type,
                    source="hub_directory",
                    repo_url=repo_url,
                    name=item["name"],
                    description=item["description"],
                    domain_tags=matched_tags if matched_tags else [],
                    stars=0,
                    is_embodied=is_embodied,
                )
                session.add(record)
                inserted_count += 1

        # Then, deep scrape detail pages for skills.sh and mcpservers.org
        detail_items = extract_detail_links(result, url)
        print(f"[DETAIL PAGES] {len(detail_items)} to scrape")

        for idx, item in enumerate(detail_items, 1):
            detail_url = item["detail_url"]
            print(f"  [{idx}/{len(detail_items)}] {detail_url}")
            
            repo_url = fetch_github_from_url(detail_url)
            if not repo_url:
                print("    -> No GitHub link found")
                continue

            existing = session.query(RosclawHubResource).filter_by(repo_url=repo_url).first()
            owner, repo_name = extract_repo_owner_name(repo_url)
            if not owner or not repo_name:
                continue

            desc = f"Found on {url.split('/')[2]}: {item['name_hint'].replace('-', ' ')}"
            is_embodied, matched_tags = classify_embodied(f"{repo_name} {desc}")

            if existing:
                sources = set((existing.source or "").split(","))
                sources.add("hub_directory")
                existing.source = ",".join(s for s in sorted(sources) if s)
                if is_embodied:
                    existing.is_embodied = True
                    existing.domain_tags = list(set((existing.domain_tags or []) + matched_tags))
                if existing.type != item["expected_type"]:
                    existing.type = item["expected_type"]
                session.merge(existing)
                print("    -> Existing updated")
            else:
                record = RosclawHubResource(
                    type=item["expected_type"],
                    source="hub_directory",
                    repo_url=repo_url,
                    name=repo_name,
                    description=desc,
                    domain_tags=matched_tags if matched_tags else [],
                    stars=0,
                    is_embodied=is_embodied,
                )
                session.add(record)
                inserted_count += 1
                print("    -> New record inserted")

            if idx % 20 == 0:
                session.commit()
            time.sleep(0.5)

        time.sleep(2)

    session.commit()
    print(f"\n[PHASE 2 COMPLETE] New records inserted: {inserted_count}")
    return inserted_count


if __name__ == "__main__":
    from database import init_db, get_session

    engine = init_db("rosclaw_hub.db")
    db_session = get_session(engine)
    run_phase_2(db_session)
    db_session.close()
