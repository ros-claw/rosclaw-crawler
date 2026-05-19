#!/usr/bin/env python3
"""
Batch LLM Crawler - Save to JSON first, then batch insert to DB
"""

import json
import urllib.request
import base64
import time
import sys
from datetime import datetime

DEEPSEEK_API_KEY = "DEEPSEEK_KEY_PLACEHOLDER"
GITHUB_TOKEN = "GITHUB_TOKEN_PLACEHOLDER"

HEADERS_GH = {
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'rosclaw-crawler',
    'Authorization': f'token {GITHUB_TOKEN}',
}

def llm_judge(name, desc, readme):
    prompt = f"""Judge if this repo is relevant to embodied AI/robotics as an MCP Server or Agent Skill.
Repo: {name}
Desc: {desc}
README: {readme[:1500]}

Reply ONLY JSON: {{"relevant":true/false,"confidence":0-100,"reason":"brief"}}"""
    
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps({
            "model": "deepseek-v4-pro",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 200,
            "response_format": {"type": "json_object"},
        }).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            content = json.loads(json.loads(resp.read().decode())["choices"][0]["message"]["content"])
            return content
    except Exception as e:
        return {"relevant": False, "confidence": 0, "reason": f"Error: {e}"}

def fetch_readme(owner, repo):
    req = urllib.request.Request(f'https://api.github.com/repos/{owner}/{repo}/readme', headers=HEADERS_GH)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return base64.b64decode(json.loads(resp.read().decode()).get('content', '')).decode('utf-8', errors='ignore')
    except:
        return ""

def search_github(query, per_page=5):
    url = f'https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=stars&order=desc&per_page={per_page}'
    req = urllib.request.Request(url, headers=HEADERS_GH)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode()).get('items', [])
    except:
        return []

def main():
    queries = [
        'mcp-server robotics', 'mcp-server robot', 'mcp-server ros', 'mcp-server ros2',
        'mcp-server drone', 'mcp-server 3d-printer', 'mcp-server manipulator', 'mcp-server servo',
        'mcp-server actuator', 'mcp-server plc', 'mcp-server arduino', 'mcp-server esp32',
        'skill.md robotics', 'skill.md robot', 'skill.md ros', 'claude-skill robot', 'agent-skill robotics',
        'mcp-server sensor', 'mcp-server motor', 'mcp-server gripper', 'mcp-server cnc',
        'mcp-server bambu', 'mcp-server klipper', 'mcp-server prusa', 'mcp-server flashforge',
        'mcp-server qidi', 'mcp-server industrial', 'mcp-server automation', 'mcp-server iot',
        'mcp-server mqtt', 'skill.md drone', 'skill.md 3d-printing', 'skill.md automation',
        'claude-skill robotics', 'claude-skill ros', 'agent-skill robot', 'agent-skill drone',
    ]
    
    results = []
    seen = set()
    
    for query in queries:
        print(f"\n[Query: {query}]")
        repos = search_github(query, 3)
        for repo in repos:
            name = repo['full_name']
            if name in seen:
                continue
            seen.add(name)
            
            print(f"  Checking {name}...", end=" ")
            owner, repo_name = name.split('/', 1)
            readme = fetch_readme(owner, repo_name)
            judgment = llm_judge(name, repo.get('description', ''), readme)
            
            item = {
                'name': name,
                'stars': repo.get('stargazers_count', 0),
                'description': repo.get('description', ''),
                'url': repo.get('html_url', ''),
                'llm': judgment,
                'readme_preview': readme[:300],
            }
            results.append(item)
            
            if judgment.get('relevant'):
                print(f"✅ ({judgment.get('confidence', 0)}%)")
            else:
                print(f"❌ ({judgment.get('confidence', 0)}%)")
            
            time.sleep(1)
    
    # Save to JSON
    filepath = f'/home/ubuntu/rosclaw/rosclaw_crawler/llm_batch_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(filepath, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*70}")
    print(f"Saved {len(results)} items to {filepath}")
    print(f"Relevant: {sum(1 for r in results if r['llm'].get('relevant'))}")
    print(f"Not relevant: {sum(1 for r in results if not r['llm'].get('relevant'))}")

if __name__ == '__main__':
    main()
