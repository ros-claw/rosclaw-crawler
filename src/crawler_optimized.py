#!/usr/bin/env python3
"""
Optimized Crawler - Smart rate limiting, proxy rotation, and deep search strategies
"""

import os
import json
import urllib.request
import base64
import time
import sqlite3
import random
from datetime import datetime
from typing import List, Dict, Optional

class OptimizedCrawler:
    """Advanced crawler with anti-rate-limiting and deep search"""
    
    def __init__(self):
        self.deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.github_token = os.getenv("GITHUB_TOKEN", "")
        self.rosclaw_key = os.getenv("ROSCALW_API_KEY", "")
        
        # Multiple GitHub tokens for rotation (if available)
        self.github_tokens = [
            self.github_token,
            os.getenv("GITHUB_TOKEN_2", ""),
            os.getenv("GITHUB_TOKEN_3", ""),
        ]
        self.github_tokens = [t for t in self.github_tokens if t]
        self.current_token_idx = 0
        
        # Rate limiting state
        self.request_count = 0
        self.last_reset = time.time()
        self.rate_limit_delay = 3  # seconds between requests
        
        self.db_path = '/home/ubuntu/rosclaw/rosclaw_crawler/data/rosclaw_hub.db'
        
    def get_github_headers(self):
        """Get headers with token rotation"""
        token = self.github_tokens[self.current_token_idx % len(self.github_tokens)]
        self.current_token_idx += 1
        return {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': f'rosclaw-crawler/{random.randint(1, 100)}',
            'Authorization': f'token {token}',
        }
    
    def rate_limit_check(self):
        """Check and enforce rate limiting"""
        now = time.time()
        
        # Reset counter every hour
        if now - self.last_reset > 3600:
            self.request_count = 0
            self.last_reset = now
        
        self.request_count += 1
        
        # Dynamic delay based on request count
        if self.request_count > 4000:  # GitHub limit is 5000/hour
            delay = 10
        elif self.request_count > 3000:
            delay = 5
        elif self.request_count > 2000:
            delay = 3
        else:
            delay = self.rate_limit_delay
        
        # Add jitter to avoid pattern detection
        jitter = random.uniform(0.5, 2.0)
        time.sleep(delay + jitter)
    
    def search_github(self, query: str, per_page: int = 10, page: int = 1) -> List[Dict]:
        """Search with retry logic and exponential backoff"""
        import urllib.parse
        
        url = f'https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=stars&order=desc&per_page={per_page}&page={page}'
        
        max_retries = 5
        for attempt in range(max_retries):
            try:
                self.rate_limit_check()
                
                req = urllib.request.Request(url, headers=self.get_github_headers())
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode())
                    return data.get('items', [])
                    
            except urllib.error.HTTPError as e:
                if e.code == 403:
                    # Rate limited - wait longer
                    wait_time = (2 ** attempt) * 10 + random.uniform(5, 15)
                    print(f"  Rate limited (403). Waiting {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    
                    # Switch token if available
                    if len(self.github_tokens) > 1:
                        self.current_token_idx += 1
                        print(f"  Switching to token {self.current_token_idx % len(self.github_tokens) + 1}")
                        
                elif e.code == 422:
                    # Unprocessable - query issue
                    print(f"  Query error (422): {query}")
                    return []
                else:
                    print(f"  HTTP Error {e.code}: {e.read().decode()[:100]}")
                    time.sleep(5)
                    
            except Exception as e:
                print(f"  Error: {e}")
                time.sleep(5)
        
        return []
    
    def fetch_readme(self, owner: str, repo: str) -> str:
        """Fetch README with caching"""
        # Check cache first
        cache_key = f"{owner}/{repo}"
        cache_file = f'/tmp/readme_cache/{owner}_{repo}.txt'
        
        if os.path.exists(cache_file):
            with open(cache_file, 'r') as f:
                return f.read()
        
        self.rate_limit_check()
        
        req = urllib.request.Request(
            f'https://api.github.com/repos/{owner}/{repo}/readme',
            headers=self.get_github_headers()
        )
        
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = base64.b64decode(
                    json.loads(resp.read().decode()).get('content', '')
                ).decode('utf-8', errors='ignore')
                
                # Cache the result
                os.makedirs('/tmp/readme_cache', exist_ok=True)
                with open(cache_file, 'w') as f:
                    f.write(content)
                
                return content
        except:
            return ""
    
    def llm_judge(self, name: str, desc: str, readme: str) -> Dict:
        """Enhanced LLM judge with retry logic"""
        prompt = f"""Evaluate if this repository is a genuine MCP Server or Agent Skill directly relevant to embodied AI/robotics.

Repository: {name}
Description: {desc}
README: {readme[:2000]}

STRICT CRITERIA:
1. MUST implement MCP protocol OR be an Agent Skill with SKILL.md
2. MUST be directly relevant to: robotics, physical AI, drones, robot simulation, robot control, autonomous vehicles, industrial automation
3. MUST be callable by an AI agent
4. EXCLUDE: pure software tools, web apps, general APIs, unrelated IoT

Reply ONLY JSON: {{"relevant":true/false,"confidence":0-100,"reason":"brief","category":"robotics|humanoid|drone|simulation|control|vision|manipulation|industrial|general"}}"""

        max_retries = 3
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(
                    "https://api.deepseek.com/chat/completions",
                    data=json.dumps({
                        "model": "deepseek-v4-pro",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.05,
                        "max_tokens": 150,
                        "response_format": {"type": "json_object"},
                    }).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.deepseek_key}"
                    },
                    method="POST",
                )
                
                with urllib.request.urlopen(req, timeout=60) as resp:
                    content = json.loads(resp.read().decode())["choices"][0]["message"]["content"]
                    result = json.loads(content)
                    
                    return {
                        "relevant": result.get("relevant", False),
                        "confidence": result.get("confidence", 0),
                        "reason": result.get("reason", "No reason"),
                        "category": result.get("category", "general")
                    }
                    
            except Exception as e:
                wait_time = (2 ** attempt) * 5
                print(f"  LLM Error (attempt {attempt+1}): {e}. Waiting {wait_time}s...")
                time.sleep(wait_time)
        
        return {"relevant": False, "confidence": 0, "reason": "Max retries exceeded", "category": "error"}
    
    def add_to_db(self, item: Dict, item_type: str = 'mcp') -> bool:
        """Add item to database"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        name = item['name']
        table = 'skills' if item_type == 'skill' else 'mcps'
        
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
            'optimized_crawler',
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
    
    def deep_search(self, queries: List[str], per_query: int = 10) -> List[Dict]:
        """Deep search with multiple pages per query"""
        results = []
        seen = set()
        
        for i, query in enumerate(queries):
            print(f"\n[{i+1}/{len(queries)}] {query}")
            
            # Search multiple pages
            for page in range(1, 4):  # Pages 1-3
                repos = self.search_github(query, per_query, page)
                
                if not repos:
                    break
                
                print(f"  Page {page}: {len(repos)} repos")
                
                for repo in repos:
                    name = repo['full_name']
                    if name in seen:
                        continue
                    seen.add(name)
                    
                    print(f"  Checking {name}...", end=" ", flush=True)
                    
                    try:
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
                            print(f"✅ ({judgment.get('confidence', 0)}%)")
                            item_type = 'skill' if 'skill' in name.lower() else 'mcp'
                            if self.add_to_db(item, item_type):
                                print(f"    -> Added to DB")
                        else:
                            print(f"❌ ({judgment.get('confidence', 0)}%)")
                            
                    except Exception as e:
                        print(f"ERROR: {e}")
            
            # Save progress every query
            if (i + 1) % 5 == 0:
                print(f"\n  [PROGRESS] {len(results)} checked, {len([r for r in results if r['llm'].get('relevant')])} relevant")
        
        return results

if __name__ == '__main__':
    crawler = OptimizedCrawler()
    print("Optimized Crawler initialized!")
    print(f"GitHub tokens available: {len(crawler.github_tokens)}")
