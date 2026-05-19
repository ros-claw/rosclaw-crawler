#!/usr/bin/env python3
"""
Re-audit all existing DB items with LLM
"""

import json
import urllib.request
import base64
import time
import sys
sys.path.insert(0, '/home/ubuntu/rosclaw/rosclaw_crawler/src')
from database import insert_item

DEEPSEEK_API_KEY = ""${DEEPSEEK_API_KEY}""
GITHUB_TOKEN = ""${GITHUB_TOKEN}""

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

def main():
    import sqlite3
    conn = sqlite3.connect('/home/ubuntu/rosclaw/rosclaw_crawler/data/rosclaw_hub.db')
    c = conn.cursor()
    
    # Get all pending items
    results = []
    for table in ['skills', 'mcps']:
        c.execute(f"SELECT full_name, description, url, stars, decision FROM {table} WHERE site_status='pending'")
        for row in c.fetchall():
            results.append({
                'table': table,
                'name': row[0],
                'description': row[1],
                'url': row[2],
                'stars': row[3],
                'old_decision': row[4],
            })
    
    print(f"Re-auditing {len(results)} items with LLM...")
    
    updated = 0
    for item in results[:20]:  # Process 20 at a time to avoid timeout
        print(f"\nChecking {item['name']}...", end=" ")
        owner, repo = item['name'].split('/', 1)
        readme = fetch_readme(owner, repo)
        judgment = llm_judge(item['name'], item['description'] or '', readme)
        
        new_decision = 'keep' if judgment.get('relevant') else 'remove'
        reason = f"LLM re-audit: {judgment.get('reason', '')}"
        
        if new_decision != item['old_decision']:
            print(f"CHANGED: {item['old_decision']} -> {new_decision} ({judgment.get('confidence', 0)}%)")
        else:
            print(f"{new_decision} ({judgment.get('confidence', 0)}%)")
        
        # Update DB
        c.execute(f"UPDATE {item['table']} SET decision=?, reason=?, confidence=? WHERE full_name=?",
                  (new_decision, reason, judgment.get('confidence', 50), item['name']))
        
        updated += 1
        time.sleep(1)
    
    conn.commit()
    conn.close()
    
    print(f"\nDone! Re-audited {updated} items.")

if __name__ == '__main__':
    main()
