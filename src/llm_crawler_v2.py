#!/usr/bin/env python3
"""
LLM-Powered Crawler v2 for Rosclaw
Uses DeepSeek API + GitHub API to discover and judge high-quality MCPs and Skills.
All LLM analysis results are saved locally for audit.
"""

import json
import urllib.request
import urllib.error
import base64
import time
import os
import sys
from datetime import datetime
from typing import Optional

sys.path.insert(0, '/home/ubuntu/rosclaw/rosclaw_crawler/src')
from database import insert_item, record_crawl_run

# DeepSeek Config
DEEPSEEK_API_KEY = "DEEPSEEK_KEY_PLACEHOLDER"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-v4-pro"

# GitHub Config
GITHUB_TOKEN = "GITHUB_TOKEN_PLACEHOLDER"
GITHUB_HEADERS = {
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'rosclaw-llm-crawler-v2',
    'Authorization': f'token {GITHUB_TOKEN}',
}

SYSTEM_PROMPT = """You are an expert judge evaluating GitHub repositories for relevance to embodied intelligence, physical AI, and robotics.

A repository is RELEVANT only if it meets ALL of these criteria:
1. It is a real MCP Server or Agent Skill (has actual MCP/skill implementation, not just a concept)
2. It is directly related to embodied intelligence, physical AI, robotics, or hardware automation
3. It can be directly used by an AI agent to interact with physical systems

NOT relevant:
- Pure software tools with no physical/hardware connection
- Collections/lists of skills without actual implementation
- Frameworks/libraries without MCP/Skill interface
- Tutorials, demos, examples
- General AI/ML without physical embodiment

Respond ONLY in JSON format:
{
  "relevant": true/false,
  "confidence": 0-100,
  "category": "robotics|drone|3d_printing|ros|industrial|simulation|sensor|actuator|other",
  "reason": "brief explanation"
}
"""


def llm_judge(name: str, description: str, readme: str, url: str) -> dict:
    """Ask DeepSeek to judge a repository."""
    user_prompt = f"""Repository: {name}
URL: {url}
Description: {description}

README (first 2000 chars):
{readme[:2000]}

Evaluate this repository. Is it truly relevant to embodied intelligence/physical AI/robotics as an MCP Server or Agent Skill?"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }

    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 500,
        "response_format": {"type": "json_object"},
    }

    req = urllib.request.Request(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        data=json.dumps(data).encode(),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            content = result["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception as e:
        return {
            "relevant": False,
            "confidence": 0,
            "category": "error",
            "reason": f"LLM API error: {str(e)}",
        }


def github_search(query: str, per_page: int = 10) -> list[dict]:
    """Search GitHub repositories."""
    url = f'https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=stars&order=desc&per_page={per_page}'
    req = urllib.request.Request(url, headers=GITHUB_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            return data.get('items', [])
    except Exception as e:
        print(f"GitHub API error: {e}")
        return []


def fetch_readme(owner: str, repo: str) -> str:
    """Fetch README content from GitHub."""
    url = f'https://api.github.com/repos/{owner}/{repo}/readme'
    req = urllib.request.Request(url, headers=GITHUB_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            return base64.b64decode(data.get('content', '')).decode('utf-8', errors='ignore')
    except Exception:
        return ""


def crawl_and_judge(queries: list[str], per_query: int = 5, output_file: str = None) -> dict:
    """Crawl GitHub and use LLM to judge each repo."""
    if output_file is None:
        output_file = f'llm_crawl_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'

    all_results = {
        'timestamp': datetime.now().isoformat(),
        'queries': queries,
        'items': [],
        'stats': {
            'total': 0,
            'relevant': 0,
            'irrelevant': 0,
            'errors': 0,
        }
    }

    seen = set()

    for query in queries:
        print(f"\n[Query] {query}")
        repos = github_search(query, per_page=per_query)

        for repo in repos:
            full_name = repo.get('full_name', '')
            if full_name in seen:
                continue
            seen.add(full_name)

            owner, repo_name = full_name.split('/', 1)
            description = repo.get('description') or ''
            url = repo.get('html_url', '')

            print(f"  Fetching README for {full_name}...")
            readme = fetch_readme(owner, repo_name)

            print(f"  Judging with LLM...")
            llm_result = llm_judge(full_name, description, readme, url)

            item = {
                'name': full_name,
                'description': description,
                'url': url,
                'stars': repo.get('stargazers_count', 0),
                'language': repo.get('language', ''),
                'readme_preview': readme[:500],
                'llm_judgment': llm_result,
                'query': query,
            }

            all_results['items'].append(item)
            all_results['stats']['total'] += 1

            if llm_result.get('relevant'):
                all_results['stats']['relevant'] += 1
                print(f"  ✅ RELEVANT ({llm_result.get('confidence', 0)}%): {llm_result.get('reason', '')}")
                
                # Save to database
                item_type = 'skill' if 'skill' in full_name.lower() or 'skill.md' in readme.lower() else 'mcp'
                insert_item(
                    item_type=item_type,
                    data={
                        'full_name': full_name,
                        'description': description,
                        'url': url,
                        'stars': repo.get('stargazers_count', 0),
                        'source': 'llm_crawler',
                        'decision': 'keep',
                        'reason': f"LLM judged relevant: {llm_result.get('reason', '')}",
                        'confidence': llm_result.get('confidence', 50),
                        'raw_data': json.dumps({'llm_analysis': llm_result, 'readme_preview': readme[:500]}),
                    }
                )
            elif llm_result.get('category') == 'error':
                all_results['stats']['errors'] += 1
                print(f"  ❌ ERROR: {llm_result.get('reason', '')}")
            else:
                all_results['stats']['irrelevant'] += 1
                print(f"  ❌ NOT RELEVANT ({llm_result.get('confidence', 0)}%): {llm_result.get('reason', '')}")
                
                # Also save to DB for audit trail
                item_type = 'skill' if 'skill' in full_name.lower() else 'mcp'
                insert_item(
                    item_type=item_type,
                    data={
                        'full_name': full_name,
                        'description': description,
                        'url': url,
                        'stars': repo.get('stargazers_count', 0),
                        'source': 'llm_crawler',
                        'decision': 'remove',
                        'reason': f"LLM judged irrelevant: {llm_result.get('reason', '')}",
                        'confidence': llm_result.get('confidence', 50),
                        'raw_data': json.dumps({'llm_analysis': llm_result, 'readme_preview': readme[:500]}),
                    }
                )

            time.sleep(1.5)  # Rate limit

        time.sleep(2)

    # Save results
    filepath = os.path.join('/home/ubuntu/rosclaw/rosclaw_crawler', output_file)
    with open(filepath, 'w') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    # Record crawl run
    record_crawl_run(
        crawl_type='llm_crawler',
        query=json.dumps(queries),
        total=all_results['stats']['total'],
        kept=all_results['stats']['relevant'],
        removed=all_results['stats']['irrelevant'],
        reviewed=0,
        details=json.dumps(all_results['stats']),
    )

    print(f"\n{'='*70}")
    print(f"Crawl complete!")
    print(f"Stats: {all_results['stats']}")
    print(f"Results saved to: {filepath}")

    return all_results


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='LLM-Powered Crawler for Rosclaw')
    parser.add_argument('--output', help='Output JSON file')
    parser.add_argument('--per-query', type=int, default=5, help='Results per query')
    args = parser.parse_args()

    QUERIES = [
        'mcp-server robotics',
        'mcp-server robot',
        'mcp-server ros',
        'mcp-server ros2',
        'mcp-server drone',
        'mcp-server 3d-printer',
        'mcp-server manipulator',
        'mcp-server servo',
        'mcp-server actuator',
        'mcp-server plc',
        'mcp-server arduino',
        'mcp-server esp32',
        'skill.md robotics',
        'skill.md robot',
        'skill.md ros',
        'claude-skill robot',
        'agent-skill robotics',
    ]

    crawl_and_judge(QUERIES, per_query=args.per_query, output_file=args.output)
