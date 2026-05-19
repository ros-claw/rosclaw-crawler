#!/usr/bin/env python3
"""
Updated Phase 1: Crawl VoltAgent/awesome-openclaw-skills categories
This awesome list stores skills in categories/*.md files
"""

import json
import base64
import re
import time
import requests
from typing import List, Dict, Set
from database import init_db, get_session, RosclawHubResource
from utils import normalize_github_url, extract_repo_owner_name
import os

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}

def fetch_file(owner: str, repo: str, path: str) -> str:
    """Fetch file content from GitHub"""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code == 200:
        data = resp.json()
        if 'content' in data:
            return base64.b64decode(data['content']).decode('utf-8')
    return None

def extract_openclaw_skills(markdown: str) -> List[Dict]:
    """Extract skill info from category markdown files"""
    skills = []
    seen = set()
    
    lines = markdown.split('\n')
    for line in lines:
        line = line.strip()
        
        # Pattern: - [Skill Name](https://clawskills.sh/skills/username-skill-slug) - Description
        match = re.search(r'- \[([^\]]+)\]\(https://clawskills\.sh/skills/([^\)]+)\)(?:\s*-\s*(.+))?', line)
        if match:
            name = match.group(1)
            full_slug = match.group(2)
            desc = (match.group(3) or "").strip('- ')
            
            # Split username-skill: first segment is username, rest is skill name
            # e.g., "mfergpt-4claw" -> username="mfergpt", skill="4claw"
            # e.g., "ira-hash-aap-passport" -> username="ira-hash", skill="aap-passport"
            parts = full_slug.split('-', 1)
            if len(parts) == 2:
                username, skill_slug = parts
            else:
                username = full_slug
                skill_slug = full_slug
            
            # Convert to openclaw/skills URL
            repo_url = f"https://github.com/openclaw/skills/tree/main/skills/{username}/{skill_slug}"
            
            if repo_url not in seen:
                seen.add(repo_url)
                skills.append({
                    'repo_url': repo_url,
                    'name': skill_slug,
                    'description': desc,
                    'source': 'awesome_openclaw_skills'
                })
    
    return skills

def crawl_voltagent_awesome_list() -> List[Dict]:
    """Crawl all categories from VoltAgent/awesome-openclaw-skills"""
    all_skills = []
    
    # Get categories list
    url = "https://api.github.com/repos/VoltAgent/awesome-openclaw-skills/contents/categories"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    
    if resp.status_code != 200:
        print(f"[ERROR] Failed to fetch categories: {resp.status_code}")
        return all_skills
    
    categories = resp.json()
    print(f"[INFO] Found {len(categories)} category files")
    
    for cat in categories:
        if cat['type'] != 'file' or not cat['name'].endswith('.md'):
            continue
        
        cat_name = cat['name'].replace('.md', '')
        print(f"[PROCESSING] Category: {cat_name}")
        
        content = fetch_file("VoltAgent", "awesome-openclaw-skills", f"categories/{cat['name']}")
        if content:
            skills = extract_openclaw_skills(content)
            print(f"  Extracted {len(skills)} skills")
            all_skills.extend(skills)
        
        time.sleep(0.5)  # Be polite
    
    return all_skills

def main():
    print("=" * 70)
    print("CRAWLING VOLTAGENT/AWESOME-OPENCLAW-SKILLS CATEGORIES")
    print("=" * 70)
    
    # Initialize database
    engine = init_db("rosclaw_hub.db")
    session = get_session(engine)
    
    # Check before
    before_count = session.query(RosclawHubResource).count()
    print(f"\n[BEFORE] Total records: {before_count}")
    
    # Crawl
    skills = crawl_voltagent_awesome_list()
    print(f"\n[TOTAL] Extracted {len(skills)} unique skills from awesome-openclaw-skills")
    
    # Insert into database
    inserted = 0
    existing = 0
    
    for skill in skills:
        # Check if exists
        existing_record = session.query(RosclawHubResource).filter_by(
            repo_url=skill['repo_url']
        ).first()
        
        if existing_record:
            # Update source
            sources = set((existing_record.source or "").split(","))
            sources.add("awesome_openclaw_skills")
            existing_record.source = ",".join(s for s in sorted(sources) if s)
            existing += 1
        else:
            # Create new
            record = RosclawHubResource(
                type="agent_skill",
                source="awesome_openclaw_skills",
                repo_url=skill['repo_url'],
                name=skill['name'],
                description=skill['description'],
                domain_tags=[],
                stars=0,
                is_embodied=False
            )
            session.add(record)
            inserted += 1
        
        if (inserted + existing) % 100 == 0:
            session.commit()
            print(f"  Progress: {inserted} new, {existing} updated")
    
    session.commit()
    
    # Check after
    after_count = session.query(RosclawHubResource).count()
    print(f"\n[AFTER] Total records: {after_count} (+{after_count - before_count})")
    print(f"[SUMMARY] New: {inserted}, Updated: {existing}")
    
    session.close()

if __name__ == "__main__":
    main()
