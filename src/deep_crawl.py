#!/usr/bin/env python3
"""
ROSClaw 深度定向抓取 - 多维度搜索
目标：找到更多真正符合三重条件的项目
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

# 深度搜索策略 - 多维度组合
DEEP_QUERIES = [
    # === 维度1: 明确MCP + 机器人硬件 ===
    '"MCP" "robot arm"',
    '"MCP" "robotic arm"',
    '"MCP" "manipulator"',
    '"MCP" "gripper"',
    '"MCP" "ROS" "control"',
    '"MCP" "ROS2" "hardware"',
    '"Model Context Protocol" "robot"',
    
    # === 维度2: Agent Skill + 物理交互 ===
    '"Agent Skill" "grasp"',
    '"Agent Skill" "pick and place"',
    '"Agent Skill" "navigation"',
    '"Agent Skill" "locomotion"',
    '"AI Skill" "robot manipulation"',
    '"AI Skill" "robot control"',
    '"Skill" "ROS" "agent"',
    
    # === 维度3: 具身智能框架 + Agent ===
    '"embodied AI" "framework"',
    '"Physical AI" "framework"',
    '"embodied intelligence" "agent"',
    '"robot learning" "agent"',
    '"robot skill" "learning"',
    
    # === 维度4: 仿真到现实 + Agent ===
    '"sim-to-real" "agent"',
    '"simulation" "robot" "agent"',
    '"Isaac Sim" "ROS"',
    '"MuJoCo" "ROS"',
    '"Gazebo" "ROS2"',
    
    # === 维度5: 特定机器人类型 + MCP/Agent ===
    '"humanoid" "MCP"',
    '"humanoid" "agent"',
    '"quadruped" "MCP"',
    '"quadruped" "agent"',
    '"drone" "MCP"',
    '"drone" "agent"',
    '"mobile robot" "MCP"',
    
    # === 维度6: 机器人感知 + Agent ===
    '"vision" "robot" "agent"',
    '"perception" "robot" "agent"',
    '"sensor" "robot" "agent"',
    '"SLAM" "agent"',
    '"navigation" "ROS2" "agent"',
    
    # === 维度7: 特定公司/实验室项目 ===
    '"NVIDIA" "robot" "agent"',
    '"NVIDIA" "Isaac" "agent"',
    '"Google" "robot" "agent"',
    '"DeepMind" "robot" "agent"',
    '"Boston Dynamics" "agent"',
    '"Unitree" "agent"',
    
    # === 维度8: 开源机器人平台 + Agent ===
    '"ROS2" "agent framework"',
    '"ROS" "agent" "skill"',
    '"MoveIt" "agent"',
    '"Nav2" "agent"',
    '"ROS Control" "agent"',
]

def github_api_search(query, per_page=100):
    """GitHub API搜索"""
    encoded_query = urllib.parse.quote(query)
    url = f"https://api.github.com/search/repositories?q={encoded_query}&sort=stars&order=desc&per_page={per_page}"
    
    req = urllib.request.Request(
        url,
        headers={
            'Authorization': f'token {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'ROSClaw-DeepCrawler'
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data.get('items', [])
    except Exception as e:
        print(f"  API error: {e}")
        return []

def save_repo(repo_data, query):
    """保存到数据库"""
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
            'deep_crawl',
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
    print("ROSClaw 深度定向抓取")
    print("=" * 80)
    
    total_new = 0
    total_skipped = 0
    
    for i, query in enumerate(DEEP_QUERIES, 1):
        print(f"\n[{i}/{len(DEEP_QUERIES)}] 搜索: {query}")
        
        time.sleep(2)  # GitHub API限速
        
        items = github_api_search(query, per_page=100)
        print(f"  找到 {len(items)} 个项目")
        
        new_count = 0
        for item in items:
            if save_repo(item, query):
                new_count += 1
                if new_count <= 5:  # 只显示前5个新增
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
    cursor.execute("SELECT COUNT(*) FROM rosclaw_hub_resources WHERE source_query LIKE 'deep_crawl%'")
    deep = cursor.fetchone()[0]
    conn.close()
    
    print(f"\n数据库统计:")
    print(f"  总项目数: {total}")
    print(f"  深度抓取新增: {total_new}")

if __name__ == '__main__':
    main()
