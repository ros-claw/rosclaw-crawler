#!/usr/bin/env python3
"""
定向搜索关键机器人组织 - 补救ros-claw遗漏
搜索已知具身智能/MCP组织，不限制stars
"""
import sqlite3
import json
import urllib.request
import urllib.parse
import time
from datetime import datetime, timezone

DB_PATH = '/home/ubuntu/.openclaw/workspace/rosclaw_crawler/rosclaw_hub.db'
GITHUB_TOKEN = '"${GITHUB_TOKEN}"'

# 关键组织列表 - 定向搜索
KEY_ORGS = [
    # ros-claw 官方
    'ros-claw',
    # NVIDIA 机器人
    'nvidia-isaac', 'nvidia-isaac-ros', 'nvidia-cosmos', 'nvidia-omniverse',
    # 宇树机器人
    'unitreerobotics', 'unitree-go2',
    # ROBOTIS
    'robotis-git', 'ROBOTIS-GIT',
    # PAL Robotics
    'pal-robotics', 'pal-gazebo',
    # 其他机器人组织
    'erlerobot', 'shadow-robot', 'husky', 'clearpathrobotics',
    'frankaemika', 'kinovarobotics', 'reachy',
    'ros-planning', 'ros-controls', 'ros-navigation',
    # 仿真
    'openai', 'mujoco', 'bulletphysics', 'gazebosim',
    # 具身智能研究组
    'facebookresearch', 'google-research', 'deepmind',
    'stanfordvl', 'berkeleyautomation', 'nvlabs',
    'mit-spark', 'ethz-asl',
]

def github_org_repos(org, per_page=100):
    """获取组织的所有仓库"""
    url = f"https://api.github.com/orgs/{org}/repos?per_page={per_page}"
    req = urllib.request.Request(
        url,
        headers={
            'Authorization': f'token {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'ROSClaw-OrgCrawler'
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"  获取 {org} 失败: {e}")
        return []

def save_repo(repo_data, org):
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
            'org_crawl',
            datetime.now(timezone.utc).isoformat(),
            f"org:{org}"
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
    print("定向搜索关键机器人组织")
    print("=" * 80)
    
    total_new = 0
    total_skipped = 0
    
    for i, org in enumerate(KEY_ORGS, 1):
        print(f"\n[{i}/{len(KEY_ORGS)}] 搜索组织: {org}")
        time.sleep(1.5)  # GitHub API限速
        
        repos = github_org_repos(org)
        print(f"  找到 {len(repos)} 个仓库")
        
        new_count = 0
        for repo in repos:
            if save_repo(repo, org):
                new_count += 1
                if new_count <= 3:
                    print(f"    + 新增: {repo['name']} (⭐{repo.get('stargazers_count', 0)})")
            else:
                total_skipped += 1
        
        total_new += new_count
        print(f"  新增: {new_count} | 已存在: {len(repos) - new_count}")
    
    print("\n" + "=" * 80)
    print(f"抓取完成: {total_new} 新增 / {total_skipped} 已存在")
    print("=" * 80)
    
    # 特别检查ros-claw组织
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, repo_url, stars, description FROM rosclaw_hub_resources WHERE repo_url LIKE '%github.com/ros-claw/%' ORDER BY stars DESC")
    rows = cursor.fetchall()
    print(f"\nros-claw 组织项目 ({len(rows)}个):")
    for row in rows:
        print(f"  {row[0]} (⭐{row[2]}) - {row[1]}")
    conn.close()

if __name__ == '__main__':
    main()
