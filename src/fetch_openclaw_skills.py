#!/usr/bin/env python3
"""
抓取 openclaw/skills 仓库中的 skill 元数据
并尝试查找 awesome-clawdbot-skills 等其他 awesome lists
"""

import json
import requests
import time
import re
from urllib.parse import urljoin
from database import init_db, get_session, RosclawHubResource
from config import GITHUB_TOKEN

HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

def fetch_github_api(url):
    """Fetch GitHub API with rate limit handling"""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code == 403 and "rate limit" in resp.text.lower():
        print(f"[RATE LIMIT] Waiting...")
        time.sleep(60)
        return fetch_github_api(url)
    return resp

def get_openclaw_skills_list():
    """Get list of all skills from openclaw/skills repository"""
    url = "https://api.github.com/repos/openclaw/skills/contents/skills?per_page=100"
    skills = []
    page = 1
    
    while True:
        resp = fetch_github_api(f"{url}&page={page}")
        if resp.status_code != 200:
            print(f"[ERROR] Failed to fetch skills list: {resp.status_code}")
            break
        
        data = resp.json()
        if not data:
            break
        
        for item in data:
            if item["type"] == "dir":
                skills.append({
                    "name": item["name"],
                    "path": item["path"],
                    "url": item["html_url"]
                })
        
        print(f"[PAGE {page}] Fetched {len(data)} items, total skills: {len(skills)}")
        
        if len(data) < 100:
            break
        page += 1
        time.sleep(0.5)
    
    return skills

def get_skill_metadata(skill_name):
    """Get metadata for a specific skill from openclaw/skills"""
    # First, list the versions available
    versions_url = f"https://api.github.com/repos/openclaw/skills/contents/skills/{skill_name}"
    resp = fetch_github_api(versions_url)
    
    if resp.status_code != 200:
        return None
    
    versions = [item for item in resp.json() if item["type"] == "dir"]
    if not versions:
        return None
    
    # Get the first (likely latest) version's metadata
    version = versions[0]["name"]
    meta_url = f"https://raw.githubusercontent.com/openclaw/skills/main/skills/{skill_name}/{version}/_meta.json"
    
    try:
        meta_resp = requests.get(meta_url, timeout=15)
        if meta_resp.status_code == 200:
            return meta_resp.json()
    except Exception as e:
        print(f"[WARN] Failed to fetch metadata for {skill_name}: {e}")
    
    return None

def extract_repo_url_from_meta(meta):
    """Extract original repository URL from skill metadata"""
    if not meta:
        return None
    
    # Try different fields that might contain the repo URL
    possible_fields = ["origin", "source", "repository", "repo", "github", "url"]
    
    for field in possible_fields:
        if field in meta and meta[field]:
            value = meta[field]
            if isinstance(value, str):
                if "github.com" in value:
                    return normalize_github_url(value)
            elif isinstance(value, dict):
                for subfield in ["url", "html_url", "clone_url", "git_url"]:
                    if subfield in value and value[subfield]:
                        url = value[subfield]
                        if "github.com" in url:
                            return normalize_github_url(url)
    
    return None

def normalize_github_url(url):
    """Normalize GitHub URL to standard format"""
    if not url:
        return None
    
    # Remove trailing slashes and .git suffix
    url = url.rstrip("/").replace(".git", "")
    
    # Convert various GitHub URL formats to standard repo URL
    patterns = [
        r"https?://(?:www\.)?github\.com/([^/]+)/([^/]+)(?:/.*)?",
        r"https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/.*",
    ]
    
    for pattern in patterns:
        match = re.match(pattern, url)
        if match:
            return f"https://github.com/{match.group(1)}/{match.group(2)}"
    
    return url if "github.com" in url else None

def search_awesome_lists():
    """Search for awesome-clawbot-skills and related awesome lists"""
    search_queries = [
        "awesome clawbot skills",
        "awesome openclaw skills",
        "awesome claw skills",
        "clawbot awesome",
        "clawd awesome"
    ]
    
    found_repos = []
    
    for query in search_queries:
        search_url = f"https://api.github.com/search/repositories?q={requests.utils.quote(query)}&per_page=10"
        resp = fetch_github_api(search_url)
        
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("items", []):
                repo_url = item["html_url"]
                if "awesome" in item["name"].lower() or "skill" in item["name"].lower():
                    found_repos.append({
                        "name": item["name"],
                        "url": repo_url,
                        "description": item.get("description", ""),
                        "stars": item.get("stargazers_count", 0)
                    })
        
        time.sleep(1)  # Rate limiting
    
    return found_repos

def check_existing_record(session, repo_url):
    """Check if a repo already exists in database"""
    if not repo_url:
        return None
    
    return session.query(RosclawHubResource).filter_by(repo_url=repo_url).first()

def main():
    print("=" * 70)
    print("OPENCLAW/SKILLS CRAWLER + AWESOME LIST DISCOVERY")
    print("=" * 70)
    
    # Initialize database
    engine = init_db("rosclaw_hub.db")
    session = get_session(engine)
    
    # Step 1: Search for awesome lists
    print("\n[STEP 1] Searching for awesome lists related to clawbot/openclaw...")
    awesome_lists = search_awesome_lists()
    print(f"Found {len(awesome_lists)} potential awesome lists:")
    for repo in awesome_lists:
        print(f"  - {repo['name']} ({repo['stars']} stars): {repo['url']}")
        print(f"    {repo['description'][:80] if repo['description'] else 'No description'}")
    
    # Step 2: Get all skills from openclaw/skills
    print("\n[STEP 2] Fetching skill list from openclaw/skills...")
    skills = get_openclaw_skills_list()
    print(f"Total skills found: {len(skills)}")
    
    # Step 3: Process each skill
    print("\n[STEP 3] Processing skill metadata...")
    new_count = 0
    existing_count = 0
    no_repo_count = 0
    
    for i, skill in enumerate(skills):
        if i % 100 == 0:
            print(f"  Progress: {i}/{len(skills)} (new: {new_count}, existing: {existing_count}, no_repo: {no_repo_count})")
            session.commit()
        
        meta = get_skill_metadata(skill["name"])
        repo_url = extract_repo_url_from_meta(meta)
        
        if not repo_url:
            no_repo_count += 1
            continue
        
        # Check if already exists
        existing = check_existing_record(session, repo_url)
        if existing:
            existing_count += 1
            # Update source if not already marked
            sources = set((existing.source or "").split(","))
            sources.add("openclaw_skills_backup")
            existing.source = ",".join(s for s in sorted(sources) if s)
            continue
        
        # Create new record
        record = RosclawHubResource(
            type="agent_skill",
            source="openclaw_skills_backup",
            repo_url=repo_url,
            name=meta.get("name", skill["name"]) if meta else skill["name"],
            description=meta.get("description", "") if meta else "",
            domain_tags=[],
            stars=0,
            is_embodied=False
        )
        session.add(record)
        new_count += 1
        
        time.sleep(0.1)  # Be polite
    
    session.commit()
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total skills in openclaw/skills: {len(skills)}")
    print(f"New records added: {new_count}")
    print(f"Existing records (updated source): {existing_count}")
    print(f"No repository URL found: {no_repo_count}")
    print(f"Potential awesome lists found: {len(awesome_lists)}")
    
    session.close()

if __name__ == "__main__":
    main()
