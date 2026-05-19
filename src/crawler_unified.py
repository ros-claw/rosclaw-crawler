#!/usr/bin/env python3
"""
Rosclaw Crawler - Unified module for discovering and curating embodied AI/robotics MCPs and Skills
"""

import os
import json
import urllib.request
import base64
import time
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional

class RosclawCrawler:
    """Main crawler class with optimized search and evaluation"""
    
    def __init__(self):
        self.deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.github_token = os.getenv("GITHUB_TOKEN", "")
        self.rosclaw_key = os.getenv("ROSCALW_API_KEY", "")
        self.headers_gh = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'rosclaw-crawler/2.0',
            'Authorization': f'token {self.github_token}',
        }
        self.db_path = '/home/ubuntu/rosclaw/rosclaw_crawler/data/rosclaw_hub.db'
        
    def search_github(self, query: str, per_page: int = 5) -> List[Dict]:
        """Search GitHub repositories"""
        import urllib.parse
        url = f'https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=stars&order=desc&per_page={per_page}'
        req = urllib.request.Request(url, headers=self.headers_gh)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode()).get('items', [])
        except Exception as e:
            print(f"Search error: {e}")
            return []
    
    def fetch_readme(self, owner: str, repo: str) -> str:
        """Fetch README content from GitHub"""
        req = urllib.request.Request(
            f'https://api.github.com/repos/{owner}/{repo}/readme',
            headers=self.headers_gh
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return base64.b64decode(
                    json.loads(resp.read().decode()).get('content', '')
                ).decode('utf-8', errors='ignore')
        except:
            return ""
    
    def llm_judge(self, name: str, desc: str, readme: str) -> Dict:
        """Use DeepSeek LLM to evaluate repository relevance"""
        prompt = f"""Judge if this repo is relevant to embodied AI/robotics as an MCP Server or Agent Skill.
Repo: {name}
Desc: {desc}
README: {readme[:1500]}

Reply ONLY JSON: {{"relevant":true/false,"confidence":0-100,"reason":"brief","category":"robotics|vision|navigation|manipulation|simulation|control|drone|3d-printing|general","robot_type":"humanoid|manipulator|mobile|drone|legged|universal"}}"""
        
        req = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps({
                "model": "deepseek-v4-pro",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 200,
                "response_format": {"type": "json_object"},
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.deepseek_key}"
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(
                    json.loads(resp.read().decode())["choices"][0]["message"]["content"]
                )
        except Exception as e:
            return {"relevant": False, "confidence": 0, "reason": f"Error: {e}"}
    
    def add_to_db(self, item: Dict, item_type: str = 'mcp') -> bool:
        """Add item to local database"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        name = item['name']
        table = 'skills' if item_type == 'skill' else 'mcps'
        
        # Check if exists
        c.execute(f"SELECT 1 FROM {table} WHERE full_name=?", (name,))
        if c.fetchone():
            conn.close()
            return False
        
        now = datetime.now().isoformat()
        c.execute(f"""
            INSERT INTO {table} 
            (source, name, full_name, description, url, stars, decision, reason, confidence, site_status, first_seen, last_checked)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'llm_crawler',
            name.split('/', 1)[1] if '/' in name else name,
            name,
            item.get('description', ''),
            item.get('url', ''),
            item.get('stars', 0),
            'keep',
            f"LLM: {item['llm'].get('reason', '')}",
            item['llm'].get('confidence', 50),
            'pending',
            now,
            now
        ))
        
        conn.commit()
        conn.close()
        return True
    
    def crawl(self, queries: List[str], per_query: int = 3) -> List[Dict]:
        """Run crawler on list of queries"""
        results = []
        seen = set()
        
        for i, query in enumerate(queries):
            print(f"[{i+1}/{len(queries)}] {query}")
            repos = self.search_github(query, per_query)
            
            for repo in repos:
                name = repo['full_name']
                if name in seen:
                    continue
                seen.add(name)
                
                print(f"  Checking {name}...", end=" ", flush=True)
                owner, repo_name = name.split('/', 1)
                readme = self.fetch_readme(owner, repo_name)
                judgment = self.llm_judge(name, repo.get('description', ''), readme)
                
                item = {
                    'name': name,
                    'stars': repo.get('stargazers_count', 0),
                    'description': repo.get('description', ''),
                    'url': repo.get('html_url', ''),
                    'llm': judgment,
                }
                results.append(item)
                
                if judgment.get('relevant') and judgment.get('confidence', 0) >= 80:
                    print(f"OK ({judgment.get('confidence', 0)}%)")
                    item_type = 'skill' if 'skill' in name.lower() else 'mcp'
                    if self.add_to_db(item, item_type):
                        print(f"    Added to DB")
                else:
                    print(f"NO ({judgment.get('confidence', 0)}%)")
                
                time.sleep(1)
        
        return results

if __name__ == '__main__':
    crawler = RosclawCrawler()
    
    # Example queries
    queries = [
        'mcp-server robotics',
        'mcp-server robot',
        'skill.md robotics',
    ]
    
    results = crawler.crawl(queries)
    print(f"\nFound {len(results)} items")
