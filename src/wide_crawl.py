#!/usr/bin/env python3
"""
ROSClaw 定向抓取模块 - 宽搜索版
扩大搜索范围，找更多具身智能Agent MCP/Skill候选
"""
import sqlite3
import json
import urllib.request
import urllib.parse
import time
from datetime import datetime, timezone
import os

DB_PATH = '/home/ubuntu/.openclaw/workspace/rosclaw_crawler/rosclaw_hub.db'
GITHUB_TOKEN = 'os.getenv("GITHUB_TOKEN", "")'

# 宽搜索查询 - 扩大覆盖面
WIDE_QUERIES = [
    # 纯ROS + Agent关键词
    'ROS2 agent',
    'ROS agent framework',
    'ROS MCP',
    'robotics agent',
    'robot agent skill',
    'embodied agent',
    'physical AI agent',
    'robot learning agent',
    'manipulation agent',
    'navigation agent robot',
    'humanoid agent',
    'quadruped agent',
    'robot skill learning',
    'simulation agent robot',
    'Isaac Sim agent',
    'MuJoCo agent',
    'Gazebo agent',
    'PyBullet agent',
    'robot control agent',
    'sensor agent robot',
    'perception agent robot',
    'planning agent robot',
    'grasping agent',
    'dexterous agent',
    'locomotion agent',
    'bipedal agent',
    'teleoperation agent',
    'sim-to-real agent',
    'robotics LLM',
    'robot language model',
    'VLA robot',
    'vision language action robot',
]

def github_api_search(query, per_page=50):
    """GitHub API搜索"""
    encoded_query = urllib.parse.quote(query)
    url = f"https://api.github.com/search/repositories?q={encoded_query}&sort=stars&order=desc&per_page={per_page}"
    
    req = urllib.request.Request(
        url,
        headers={
            'Authorization': f'token {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'ROSClaw-Crawler'
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data.get('items', [])
    except Exception as e:
        print(f"  API error for '{query}': {e}")
        return []

def save_repo(repo_data, query):
    """保存项目到数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO rosclaw_hub_resources 
            (name, description, repo_url, stars, source, crawled_at, source_query)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            repo_data['name'],
            repo_data.get('description', ''),
            repo_data['html_url'],
            repo_data.get('stargazers_count', 0),
            'github_api_wide',
            datetime.now(timezone.utc).isoformat(),
            query
        ))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"  DB error: {e}")
        return False
    finally:
        conn.close()

def main():
    print("=" * 80)
    print("ROSClaw 宽搜索定向抓取")
    print("=" * 80)
    
    total_new = 0
    total_skipped = 0
    
    for i, query in enumerate(WIDE_QUERIES, 1):
        print(f"\n[{i}/{len(WIDE_QUERIES)}] 搜索: {query}")
        
        time.sleep(2)  # GitHub API限速
        
        items = github_api_search(query, per_page=50)
        print(f"  找到 {len(items)} 个项目")
        
        new_count = 0
        for item in items:
            if save_repo(item, query):
                new_count += 1
                print(f"    + 新增: {item['name']} (⭐{item.get('stargazers_count', 0)})")
            else:
                total_skipped += 1
        
        total_new += new_count
        print(f"  本次新增: {new_count} | 跳过: {len(items) - new_count}")
    
    print("\n" + "=" * 80)
    print(f"抓取完成: {total_new} 新增 / {total_skipped} 跳过")
    print("=" * 80)
    
    # 统计
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM rosclaw_hub_resources")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM rosclaw_hub_resources WHERE source_query IS NOT NULL")
    targeted = cursor.fetchone()[0]
    conn.close()
    
    print(f"\n数据库统计:")
    print(f"  总项目数: {total}")
    print(f"  定向抓取项目: {targeted}")

if __name__ == '__main__':
    main()
