#!/usr/bin/env python3
"""
Hybrid Classifier v3.1 - Improved keyword matching + README analysis
"""

import os
import json
import urllib.request
import base64
import sqlite3
from datetime import datetime

DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '')
DB_PATH = '/home/ubuntu/rosclaw/rosclaw_crawler/data/rosclaw_hub.db'

# Strong indicators that DON'T need LLM
STRONG_MCP_INDICATORS = [
    'model context protocol', 'mcp server', 'mcp-server',
    'stdio transport', 'sse transport', '@modelcontextprotocol',
    'mcp.tool', 'mcp.resource', 'mcp-server'
]

STRONG_SKILL_INDICATORS = [
    'skill.md', 'claude code skill', 'claude-code skill',
    'agent skill', 'skills for claude', 'claude skill'
]

ROBOTICS_KEYWORDS = [
    'robot', 'robotics', 'ros', 'ros2', 'mujoco', 'gazebo', 'isaac',
    'drone', 'uav', 'mavlink', 'px4', 'ardupilot', 'turtlebot',
    'kinova', 'franka', 'ur5', 'ur10', 'unitree', 'boston dynamics',
    'humanoid', 'manipulator', 'gripper', 'grasping', 'slam',
    'lidar', 'realsense', 'servo', 'actuator', 'encoder',
    '3d printer', '3d printing', 'bambu', 'prusa', 'klipper', 'cnc',
    'arduino', 'esp32', 'jetson', 'plc', 'modbus',
    'reachy', 'pepper', 'nao', 'vector', 'anki',
    'openai robotics', 'physical ai', 'embodied',
]

EXCLUSION_KEYWORDS = [
    'microsoft dynamics', 'd365', 'business central',
    'excel', 'powerpoint', 'word', 'office 365',
    'vue.js', 'react.js', 'angular', 'frontend framework',
    'game engine', 'gaming', 'entertainment',
    'social media', 'chat app', 'messaging app',
]

def get_cached_judgment(full_name: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT item_type, is_robotics, confidence, reason FROM llm_judgments WHERE full_name=?", (full_name,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return {
            'item_type': row[0],
            'is_robotics': bool(row[1]),
            'confidence': row[2],
            'reason': row[3],
            'cached': True
        }
    return None

def save_judgment(full_name: str, item_type: str, is_robotics: bool, confidence: int, reason: str, readme_snippet: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO llm_judgments 
        (full_name, judged_at, item_type, is_robotics, confidence, reason, readme_snippet)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (full_name, datetime.now().isoformat(), item_type, int(is_robotics), confidence, reason, readme_snippet[:500]))
    conn.commit()
    conn.close()

def fetch_repo_info(owner: str, repo: str) -> dict:
    """Fetch repo metadata and README"""
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'Authorization': f'token {os.getenv("GITHUB_TOKEN", "")}',
        'User-Agent': 'rosclaw-classifier'
    }
    
    info = {'description': '', 'readme': '', 'stars': 0, 'error': None}
    
    try:
        req = urllib.request.Request(
            f'https://api.github.com/repos/{owner}/{repo}',
            headers=headers
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            info['description'] = data.get('description', '') or ''
            info['stars'] = data.get('stargazers_count', 0)
    except Exception as e:
        info['error'] = str(e)[:50]
    
    try:
        req = urllib.request.Request(
            f'https://api.github.com/repos/{owner}/{repo}/readme',
            headers=headers
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            content = base64.b64decode(data.get('content', '')).decode('utf-8', errors='ignore')
            info['readme'] = content[:2000]
    except:
        pass
    
    return info

def quick_keyword_check(name: str, description: str, readme: str) -> dict:
    text = f"{name} {description} {readme}".lower()
    
    # Check exclusions
    for kw in EXCLUSION_KEYWORDS:
        if kw.lower() in text:
            return {'need_llm': False, 'item_type': 'neither', 'reason': f'Excluded: {kw}'}
    
    # Check strong indicators
    has_mcp_indicator = any(ind.lower() in text for ind in STRONG_MCP_INDICATORS)
    has_skill_indicator = any(ind.lower() in text for ind in STRONG_SKILL_INDICATORS)
    
    # Check robotics (allow partial matches)
    robotics_score = 0
    for kw in ROBOTICS_KEYWORDS:
        if kw.lower() in text:
            robotics_score += 1
    
    # Decision logic
    if has_mcp_indicator and robotics_score >= 1:
        return {'need_llm': False, 'item_type': 'mcp', 'reason': 'Strong MCP + robotics'}
    
    if has_skill_indicator and robotics_score >= 1:
        return {'need_llm': False, 'item_type': 'skill', 'reason': 'Strong Skill + robotics'}
    
    # Name-based hints
    repo_part = name.split('/')[-1].lower()
    if 'skill' in repo_part and robotics_score >= 1:
        return {'need_llm': False, 'item_type': 'skill', 'reason': 'Name suggests skill + robotics'}
    
    if 'mcp' in repo_part and robotics_score >= 1:
        return {'need_llm': True, 'item_type': 'unknown', 'reason': 'Name has MCP, need README check'}
    
    if robotics_score == 0:
        return {'need_llm': False, 'item_type': 'neither', 'reason': 'No robotics keywords'}
    
    return {'need_llm': True, 'item_type': 'unknown', 'reason': 'Borderline case'}

def llm_judge(name: str, description: str, readme: str) -> dict:
    cached = get_cached_judgment(name)
    if cached:
        return cached
    
    if not DEEPSEEK_API_KEY:
        return {'item_type': 'neither', 'is_robotics': False, 'confidence': 0, 'reason': 'No API key'}
    
    prompt = f"""Repository: {name}
Description: {description[:200]}
README: {readme[:1500]}

Question 1: Is this about robotics/drones/3D printers/physical AI? (yes/no)
Question 2: Is this an MCP Server implementing Model Context Protocol? (yes/no)  
Question 3: Is this an Agent Skill for Claude Code or similar? (yes/no)
Question 4: Is this empty/placeholder (README < 200 chars or only TODO)? (yes/no)

Reply ONLY: robotics=yes/no mcp=yes/no skill=yes/no empty=yes/no"""

    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps({
                "model": "deepseek-v4-pro",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 50,
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
            },
            method="POST",
        )
        
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode())
            content = data["choices"][0]["message"]["content"].lower()
            
            is_robotics = 'robotics=yes' in content
            is_mcp = 'mcp=yes' in content
            is_skill = 'skill=yes' in content
            is_empty = 'empty=yes' in content
            
            if is_empty:
                item_type = 'neither'
                confidence = 90
                reason = 'Empty/placeholder repository'
            elif is_mcp and is_robotics:
                item_type = 'mcp'
                confidence = 90
                reason = 'LLM confirms MCP + robotics'
            elif is_skill and is_robotics:
                item_type = 'skill'
                confidence = 90
                reason = 'LLM confirms Skill + robotics'
            else:
                item_type = 'neither'
                confidence = 70
                reason = f'LLM: robotics={is_robotics}, mcp={is_mcp}, skill={is_skill}'
            
            save_judgment(name, item_type, is_robotics, confidence, reason, readme[:200])
            
            return {
                'item_type': item_type,
                'is_robotics': is_robotics,
                'confidence': confidence,
                'reason': reason
            }
    except Exception as e:
        return {'item_type': 'neither', 'is_robotics': False, 'confidence': 0, 'reason': f'LLM error: {str(e)[:50]}'}

def classify(name: str, description: str = "", readme: str = "") -> dict:
    quick = quick_keyword_check(name, description, readme)
    
    if not quick['need_llm']:
        return {
            'item_type': quick['item_type'],
            'decision': 'keep' if quick['item_type'] in ['mcp', 'skill'] else 'remove',
            'confidence': 85,
            'reason': f"Keyword: {quick['reason']}",
            'site_status': 'pending' if quick['item_type'] in ['mcp', 'skill'] else 'removed'
        }
    
    llm_result = llm_judge(name, description, readme)
    
    if not llm_result['is_robotics']:
        return {
            'item_type': 'neither',
            'decision': 'remove',
            'confidence': llm_result['confidence'],
            'reason': f"LLM: Not robotics - {llm_result['reason']}",
            'site_status': 'removed'
        }
    
    if llm_result['item_type'] not in ['mcp', 'skill']:
        return {
            'item_type': 'neither',
            'decision': 'remove',
            'confidence': llm_result['confidence'],
            'reason': f"LLM: Not MCP/Skill - {llm_result['reason']}",
            'site_status': 'removed'
        }
    
    return {
        'item_type': llm_result['item_type'],
        'decision': 'keep',
        'confidence': llm_result['confidence'],
        'reason': f"LLM: {llm_result['reason']}",
        'site_status': 'pending'
    }
