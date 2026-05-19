#!/usr/bin/env python3
"""
Crawl VoltAgent/awesome-openclaw-skills categories and save to JSON first
then bulk insert to database
"""

import json
import base64
import re
import time
import requests
from typing import List, Dict, Set
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
                    'username': username,
                    'full_slug': full_slug
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
            for s in skills:
                s['category'] = cat_name
            all_skills.extend(skills)
        
        time.sleep(0.3)  # Be polite
    
    return all_skills

def main():
    print("=" * 70)
    print("CRAWLING VOLTAGENT/AWESOME-OPENCLAW-SKILLS CATEGORIES")
    print("=" * 70)
    
    # Crawl
    skills = crawl_voltagent_awesome_list()
    print(f"\n[TOTAL] Extracted {len(skills)} skills from awesome-openclaw-skills")
    
    # Save to JSON
    output_file = "voltagent_skills.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(skills, f, indent=2, ensure_ascii=False)
    
    print(f"[SAVED] {len(skills)} skills to {output_file}")
    
    # Category stats
    from collections import Counter
    cat_counts = Counter(s['category'] for s in skills)
    print("\n[CATEGORY BREAKDOWN]")
    for cat, count in cat_counts.most_common():
        print(f"  {cat}: {count}")

if __name__ == "__main__":
    main()
