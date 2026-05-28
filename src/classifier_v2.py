#!/usr/bin/env python3
"""
Robust Classifier v2 - Uses LLM to analyze README + About content
NOT just name matching
"""

import os
import json
import urllib.request
import base64
from typing import Dict, Tuple

DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '')


def fetch_repo_info(owner: str, repo: str) -> Dict:
    """Fetch repo metadata and README from GitHub API"""
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'Authorization': f'token {os.getenv("GITHUB_TOKEN", "")}',
        'User-Agent': 'rosclaw-classifier'
    }
    
    info = {
        'name': f'{owner}/{repo}',
        'description': '',
        'readme': '',
        'stars': 0,
        'topics': [],
        'error': None
    }
    
    try:
        # Fetch repo metadata
        req = urllib.request.Request(
            f'https://api.github.com/repos/{owner}/{repo}',
            headers=headers
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            info['description'] = data.get('description', '') or ''
            info['stars'] = data.get('stargazers_count', 0)
            info['topics'] = data.get('topics', [])
    except Exception as e:
        info['error'] = f'Metadata error: {str(e)[:50]}'
        return info
    
    try:
        # Fetch README
        req = urllib.request.Request(
            f'https://api.github.com/repos/{owner}/{repo}/readme',
            headers=headers
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            content = base64.b64decode(data.get('content', '')).decode('utf-8', errors='ignore')
            info['readme'] = content[:3000]  # First 3000 chars
    except Exception as e:
        info['readme'] = ''
    
    return info


def llm_classify(name: str, description: str, readme: str) -> Dict:
    """
    Use LLM to classify based on README + About content
    NOT just name matching
    """
    prompt = f"""Analyze this GitHub repository and classify it.

Repository: {name}
About/Description: {description}
README (first 2000 chars):
{readme[:2000]}

You must reply with ONLY a JSON object in this exact format:
{{
  "is_mcp": true/false,
  "is_skill": true/false,
  "is_robotics": true/false,
  "item_type": "mcp" or "skill" or "neither",
  "confidence": 0-100,
  "reason": "brief explanation",
  "has_real_content": true/false,
  "is_empty_or_placeholder": true/false
}}

Classification rules:
- MCP Server: MUST implement Model Context Protocol, have server.py or similar, mention stdio/SSE transport, expose tools/resources
- Skill: MUST be an Agent Skill (Claude Code skill, SKILL.md, etc.), NOT just a library or app
- Robotics: MUST be directly about robots, ROS, drones, robot simulation, physical AI, automation
- Empty/Placeholder: README < 200 chars, only "TODO", "WIP", "coming soon", no real code

Be STRICT. If unsure, mark as "neither"."""

    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps({
                "model": "deepseek-v4-pro",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 300,
                "response_format": {"type": "json_object"},
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
            },
            method="POST",
        )
        
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            content = data["choices"][0]["message"]["content"]
            result = json.loads(content)
            
            return {
                'is_mcp': result.get('is_mcp', False),
                'is_skill': result.get('is_skill', False),
                'is_robotics': result.get('is_robotics', False),
                'item_type': result.get('item_type', 'neither'),
                'confidence': result.get('confidence', 0),
                'reason': result.get('reason', 'No reason'),
                'has_real_content': result.get('has_real_content', True),
                'is_empty_or_placeholder': result.get('is_empty_or_placeholder', False)
            }
            
    except Exception as e:
        return {
            'is_mcp': False,
            'is_skill': False,
            'is_robotics': False,
            'item_type': 'neither',
            'confidence': 0,
            'reason': f'LLM Error: {str(e)[:100]}',
            'has_real_content': False,
            'is_empty_or_placeholder': True
        }


def classify_repository(name: str, use_llm: bool = True) -> Dict:
    """
    Full classification pipeline:
    1. Fetch repo info (README + metadata)
    2. LLM analysis of content
    3. Return structured result
    """
    if '/' not in name:
        return {
            'item_type': 'neither',
            'decision': 'remove',
            'confidence': 0,
            'reason': 'Invalid repo name format',
            'site_status': 'removed'
        }
    
    owner, repo = name.split('/', 1)
    
    # Step 1: Fetch repo info
    info = fetch_repo_info(owner, repo)
    
    if info['error'] and not info['readme']:
        return {
            'item_type': 'neither',
            'decision': 'remove',
            'confidence': 50,
            'reason': f'Failed to fetch repo info: {info["error"]}',
            'site_status': 'removed'
        }
    
    # Step 2: LLM Classification (if enabled)
    if use_llm and DEEPSEEK_API_KEY:
        llm_result = llm_classify(name, info['description'], info['readme'])
        
        # Check if empty/placeholder
        if llm_result['is_empty_or_placeholder'] or not llm_result['has_real_content']:
            return {
                'item_type': 'neither',
                'decision': 'remove',
                'confidence': 90,
                'reason': f'Empty/placeholder repo: {llm_result["reason"]}',
                'site_status': 'removed'
            }
        
        # Check if robotics-related
        if not llm_result['is_robotics']:
            return {
                'item_type': 'neither',
                'decision': 'remove',
                'confidence': llm_result['confidence'],
                'reason': f'Not robotics-related: {llm_result["reason"]}',
                'site_status': 'removed'
            }
        
        # Determine type
        item_type = llm_result['item_type']
        if item_type not in ['mcp', 'skill']:
            item_type = 'neither'
        
        if item_type == 'neither':
            return {
                'item_type': 'neither',
                'decision': 'remove',
                'confidence': llm_result['confidence'],
                'reason': f'Not MCP or Skill: {llm_result["reason"]}',
                'site_status': 'removed'
            }
        
        # Valid MCP or Skill
        return {
            'item_type': item_type,
            'decision': 'keep',
            'confidence': llm_result['confidence'],
            'reason': f'LLM verified: {llm_result["reason"]}',
            'site_status': 'pending',
            'description': info['description'],
            'stars': info['stars'],
            'url': f'https://github.com/{name}'
        }
    
    # Fallback: name-based classification (if LLM disabled)
    else:
        from classifier import classify_repo
        item_type, confidence, reason = classify_repo(name, info['description'], info['readme'])
        
        if item_type == 'neither':
            return {
                'item_type': 'neither',
                'decision': 'remove',
                'confidence': confidence,
                'reason': reason,
                'site_status': 'removed'
            }
        
        return {
            'item_type': item_type,
            'decision': 'keep',
            'confidence': confidence,
            'reason': reason,
            'site_status': 'pending',
            'description': info['description'],
            'stars': info['stars'],
            'url': f'https://github.com/{name}'
        }


# Test
if __name__ == '__main__':
    import sys
    
    test_repos = [
        'jherrodthomas/robotics-skills-suite',
        'DMontgomery40/mcp-3D-printer-server',
        'dynamics365ninja/d365fo-mcp-server',
        'robotmcp/ros-mcp-server',
    ]
    
    print("Testing classifier_v2 with LLM...")
    print("="*70)
    
    for repo in test_repos:
        print(f"\n📦 {repo}")
        result = classify_repository(repo, use_llm=True)
        print(f"   Type: {result['item_type']}")
        print(f"   Decision: {result['decision']}")
        print(f"   Confidence: {result.get('confidence', 'N/A')}")
        print(f"   Reason: {result['reason'][:80]}")
