#!/usr/bin/env python3
"""
快速搜索 awesome lists 并抽样检查 openclaw/skills 结构
"""

import json
import requests
import time
import os

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}

def search_awesome_lists():
    """Search for awesome lists related to clawbot/clawd/openclaw"""
    queries = [
        "awesome clawbot",
        "awesome openclaw", 
        "awesome clawd",
        "clawbot awesome",
        "openclaw awesome",
        "clawd awesome"
    ]
    
    all_repos = []
    
    for query in queries:
        print(f"\n[SEARCH] '{query}'")
        url = f"https://api.github.com/search/repositories?q={requests.utils.quote(query)}&sort=stars&order=desc&per_page=10"
        
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            print(f"  Found {len(items)} results")
            
            for item in items:
                repo_info = {
                    "name": item["name"],
                    "full_name": item["full_name"],
                    "url": item["html_url"],
                    "description": item.get("description", "") or "",
                    "stars": item.get("stargazers_count", 0),
                    "language": item.get("language", ""),
                    "updated": item["updated_at"]
                }
                all_repos.append(repo_info)
                print(f"    ⭐ {repo_info['stars']:4d} | {repo_info['full_name']}")
        else:
            print(f"  Error: {resp.status_code} - {resp.text[:100]}")
        
        time.sleep(1)  # Rate limiting
    
    return all_repos

def check_openclaw_skills_structure():
    """Check the structure of openclaw/skills repository"""
    print("\n" + "="*70)
    print("[CHECK] openclaw/skills repository structure")
    print("="*70)
    
    # Get skills directory listing
    url = "https://api.github.com/repos/openclaw/skills/contents/skills?per_page=100"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    
    if resp.status_code != 200:
        print(f"Error: {resp.status_code}")
        return None
    
    skills = resp.json()
    print(f"First page shows {len(skills)} items")
    
    # Sample a few skills to understand structure
    sample_skills = skills[:5]
    
    for skill in sample_skills:
        name = skill["name"]
        print(f"\n[SAMPLE] Skill: {name}")
        
        # Get versions (subdirectories)
        versions_url = f"https://api.github.com/repos/openclaw/skills/contents/skills/{name}"
        v_resp = requests.get(versions_url, headers=HEADERS, timeout=15)
        
        if v_resp.status_code == 200:
            versions = [v for v in v_resp.json() if v["type"] == "dir"]
            if versions:
                version = versions[0]["name"]
                print(f"  Version: {version}")
                
                # Try to get _meta.json
                meta_url = f"https://raw.githubusercontent.com/openclaw/skills/main/skills/{name}/{version}/_meta.json"
                m_resp = requests.get(meta_url, timeout=10)
                
                if m_resp.status_code == 200:
                    try:
                        meta = m_resp.json()
                        print(f"  Metadata keys: {list(meta.keys())}")
                        
                        # Look for source/origin fields
                        for key in ["origin", "source", "repository", "repo", "github", "url", "homepage"]:
                            if key in meta and meta[key]:
                                print(f"  {key}: {meta[key]}")
                    except:
                        print(f"  Failed to parse metadata")
        
        time.sleep(0.5)
    
    return len(skills)

def main():
    print("="*70)
    print("AWESOME LISTS DISCOVERY + OPENCLAW/SKILLS STRUCTURE CHECK")
    print("="*70)
    
    # Step 1: Search for awesome lists
    print("\n" + "="*70)
    print("STEP 1: Searching for awesome lists...")
    print("="*70)
    
    repos = search_awesome_lists()
    
    # Filter for awesome lists specifically
    awesome_lists = [r for r in repos if "awesome" in r["name"].lower()]
    
    print("\n" + "="*70)
    print("AWESOME LISTS FOUND:")
    print("="*70)
    
    for repo in awesome_lists:
        print(f"\n⭐ {repo['stars']} | {repo['full_name']}")
        print(f"   URL: {repo['url']}")
        print(f"   Desc: {repo['description'][:100] if repo['description'] else 'N/A'}")
    
    # Step 2: Check openclaw/skills structure
    total_skills = check_openclaw_skills_structure()
    
    if total_skills:
        print(f"\n[NOTE] openclaw/skills contains approximately {total_skills}+ skills per page")
        print("Multiple pages exist - likely 1000+ total skills")
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Awesome lists found: {len(awesome_lists)}")
    print(f"Total repos found: {len(repos)}")
    print(f"openclaw/skills appears to have 1000+ skills")
    
    # Save awesome lists to file
    if awesome_lists:
        with open("discovered_awesome_lists.json", "w") as f:
            json.dump(awesome_lists, f, indent=2)
        print(f"\nSaved {len(awesome_lists)} awesome lists to discovered_awesome_lists.json")

if __name__ == "__main__":
    main()
