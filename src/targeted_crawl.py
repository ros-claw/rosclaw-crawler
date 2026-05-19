#!/usr/bin/env python3
"""
ROSClaw 定向抓取模块
专门抓取具身智能 + Agent + MCP/Skill 项目
合并到现有数据库，去重
"""
import sqlite3
import json
import urllib.request
import urllib.parse
import time
from datetime import datetime, timezone

DB_PATH = '/home/ubuntu/.openclaw/workspace/rosclaw_crawler/rosclaw_hub.db'
GITHUB_TOKEN = 'GITHUB_TOKEN_PLACEHOLDER'

# 定向搜索查询 - 必须同时命中具身+Agent
TARGETED_QUERIES = [
    # MCP + 机器人
    '"MCP" "ROS" robot',
    '"Model Context Protocol" "robotics"',
    '"MCP server" "ROS2"',
    # Agent Skill + 机器人
    '"Agent Skill" "robot"',
    '"AI Skill" "manipulation"',
    '"Agent Skill" "navigation"',
    # OpenClaw/Claude + 物理
    '"OpenClaw" "robot"',
    '"Claude Code" "ROS"',
    '"Claude" "embodied"',
    # 具身智能 + MCP
    '"embodied AI" "MCP"',
    '"Physical AI" "agent"',
    '"humanoid" "MCP"',
    '"quadruped" "agent"',
    # 仿真 + Agent
    '"Isaac Sim" "agent"',
    '"MuJoCo" "MCP"',
    '"Gazebo" "agent skill"',
]

def github_api_search(query, per_page=30):
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

def init_db():
    """初始化/检查数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 检查表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rosclaw_hub_resources'")
    if not cursor.fetchone():
        print("创建新表...")
        cursor.execute('''
            CREATE TABLE rosclaw_hub_resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                description TEXT,
                repo_url TEXT UNIQUE,
                stars INTEGER,
                source TEXT,
                crawled_at TEXT,
                source_query TEXT,
                llm_analyzed_at TEXT,
                llm_relevance_score INTEGER,
                llm_category TEXT,
                llm_summary TEXT,
                llm_key_features TEXT,
                llm_model TEXT
            )
        ''')
        conn.commit()
    else:
        # 检查并添加缺失的列
        cursor.execute('PRAGMA table_info(rosclaw_hub_resources)')
        columns = [col[1] for col in cursor.fetchall()]
        
        new_columns = {
            'crawled_at': 'TEXT',
            'source_query': 'TEXT'
        }
        
        for col_name, col_type in new_columns.items():
            if col_name not in columns:
                cursor.execute(f'ALTER TABLE rosclaw_hub_resources ADD COLUMN {col_name} {col_type}')
                print(f'添加列: {col_name}')
        
        conn.commit()
    
    conn.close()

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
            'github_api',
            datetime.now(timezone.utc).isoformat(),
            query
        ))
        conn.commit()
        return cursor.rowcount > 0  # True if inserted
    except Exception as e:
        print(f"  DB error: {e}")
        return False
    finally:
        conn.close()

def main():
    print("=" * 80)
    print("ROSClaw 定向抓取 - 具身智能Agent MCP/Skill")
    print("=" * 80)
    
    init_db()
    
    total_new = 0
    total_skipped = 0
    
    for i, query in enumerate(TARGETED_QUERIES, 1):
        print(f"\n[{i}/{len(TARGETED_QUERIES)}] 搜索: {query}")
        
        # GitHub API限制：每秒最多1-2请求
        time.sleep(2)
        
        items = github_api_search(query, per_page=30)
        print(f"  找到 {len(items)} 个项目")
        
        new_count = 0
        for item in items:
            if save_repo(item, query):
                new_count += 1
                print(f"    + 新增: {item['name']} (⭐{item.get('stargazers_count', 0)})")
            else:
                total_skipped += 1
        
        total_new += new_count
        print(f"  本次新增: {new_count} | 跳过(已存在): {len(items) - new_count}")
    
    print("\n" + "=" * 80)
    print(f"抓取完成: {total_new} 新增 / {total_skipped} 已存在跳过")
    print("=" * 80)
    
    # 统计数据库现状
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
