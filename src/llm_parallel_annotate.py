#!/usr/bin/env python3
"""
ROSClaw LLM Parallel Re-Annotation Pipeline
并行版本 - 5并发处理
"""

import json
import sqlite3
import requests
from datetime import datetime
import time
import sys
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

API_KEY = "BAILIAN_KEY_PLACEHOLDER"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.5-plus"
MAX_WORKERS = 10  # 10并发

# 线程锁用于数据库写入
db_lock = threading.Lock()

# 统计
stats = {
    'total': 0,
    'success': 0,
    'failed': 0,
    'high_score': 0,
    'medium_score': 0,
    'low_score': 0
}
stats_lock = threading.Lock()

running = True

def signal_handler(sig, frame):
    global running
    print("\n🛑 收到停止信号...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def create_prompt(repo_type, name, description, url, stars):
    """创建标注Prompt"""
    if repo_type == 'mcp_server':
        template = "MCP Server: focus on physical capabilities, robot control, ROS/Isaac/MuJoCo integration."
    else:
        template = "Agent Skill: focus on physical tasks, robot types, cross-platform capabilities."
    
    desc = description or "No description"
    
    prompt = """You are a ROSClaw Physical AI expert.
Rate this repository for ROSClaw ecosystem relevance.

Repository: %s
Type: %s
Stars: %d
Description: %s

%s

Key ROSClaw concepts (HIGH relevance if matching):
- Embodied AI, Physical AI, Robotics, Humanoid robots
- ROS/ROS2, VLA/VLN, World Models
- Isaac Sim, MuJoCo, Gazebo, Sim-to-Real
- Manipulation, Navigation, Control, Perception, SLAM
- RL, Imitation Learning, ACT
- Robot hardware: RealSense, LiDAR, Jetson, sensors
- IoT for robotics, Industrial Automation

STRICT scoring for ROSClaw:
- 90-100: Direct embodied AI (robot manipulation, navigation, control)
- 80-89: Strongly related - IoT/robot hardware/algorithms/ROS/simulation
- 70-79: Robot learning frameworks, drivers, sim-to-real
- 50-69: CV/ML tools usable for robots
- 0-49: Not relevant - web apps, general software

Output JSON:
{
  "summary": "What this does (2 sentences)",
  "relevance_score": 0-100,
  "category": "Primary category",
  "subcategory": "Specific type",
  "robot_types": ["Robot types or None"],
  "tags": ["5-10 tags"],
  "capabilities": ["Key functions"],
  "mcp_tools": null or [{"name": "x", "description": "y"}],
  "hardware_requirements": [],
  "software_dependencies": [],
  "is_rosclaw_native": true/false,
  "confidence": 0-100
}

Return ONLY JSON.""" % (name, repo_type, stars, desc, template)
    
    return prompt

def call_llm(prompt, max_retries=3):
    """调用阿里百炼API"""
    headers = {
        "Authorization": "Bearer " + API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a robotics expert."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 1200
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(
                BASE_URL + "/chat/completions",
                headers=headers,
                json=payload,
                timeout=90
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                
                # 清理markdown
                content = content.strip()
                if content.startswith("```json"):
                    content = content[7:]
                elif content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                
                return json.loads(content)
                
            elif response.status_code == 429:
                time.sleep(5)
                continue
            else:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
    
    return None

def update_repo(db_path, repo_id, result):
    """更新数据库 - 线程安全"""
    features = {
        'subcategory': result.get('subcategory', ''),
        'robot_types': result.get('robot_types', []),
        'tags': result.get('tags', []),
        'capabilities': result.get('capabilities', []),
        'mcp_tools': result.get('mcp_tools'),
        'hardware_requirements': result.get('hardware_requirements', []),
        'software_dependencies': result.get('software_dependencies', []),
        'confidence': result.get('confidence', 0)
    }
    
    score = result.get('relevance_score', 0)
    is_rosclaw_native = result.get('is_rosclaw_native', False) or score >= 70
    
    with db_lock:
        for attempt in range(5):
            try:
                conn = sqlite3.connect(db_path, timeout=30)
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE rosclaw_hub_resources SET
                        llm_summary = ?,
                        llm_relevance_score = ?,
                        llm_category = ?,
                        llm_key_features = ?,
                        llm_analyzed_at = ?,
                        llm_model = ?,
                        domain_tags = ?,
                        is_embodied = ?
                    WHERE id = ?
                """, (
                    result.get('summary', ''),
                    score,
                    result.get('category', 'Unknown'),
                    json.dumps(features, ensure_ascii=False),
                    datetime.now().isoformat(),
                    MODEL,
                    json.dumps(result.get('tags', []), ensure_ascii=False),
                    is_rosclaw_native,
                    repo_id
                ))
                
                conn.commit()
                conn.close()
                return score
                
            except sqlite3.OperationalError:
                if attempt < 4:
                    time.sleep(1 * (attempt + 1))
                else:
                    raise
    
    return None

def get_pending_repos(db_path, batch_size=50):
    """获取待标注仓库"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, type, repo_url, name, description, stars
        FROM rosclaw_hub_resources
        WHERE is_relevant = 1
        AND (llm_model IS NULL OR llm_model != ?)
        ORDER BY stars DESC
        LIMIT ?
    """, (MODEL, batch_size))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [{'id': r[0], 'type': r[1], 'repo_url': r[2], 
             'name': r[3], 'description': r[4], 'stars': r[5]} for r in rows]

def process_single_repo(db_path, repo):
    """处理单个仓库"""
    global stats, running
    
    if not running:
        return False
    
    prompt = create_prompt(
        repo['type'], repo['name'], repo['description'],
        repo['repo_url'], repo['stars']
    )
    
    result = call_llm(prompt)
    
    if result:
        score = update_repo(db_path, repo['id'], result)
        
        with stats_lock:
            stats['success'] += 1
            stats['total'] += 1
            
            if score >= 80:
                stats['high_score'] += 1
            elif score >= 50:
                stats['medium_score'] += 1
            else:
                stats['low_score'] += 1
        
        return True
    else:
        with stats_lock:
            stats['failed'] += 1
            stats['total'] += 1
        return False

def process_batch_parallel(db_path, repos):
    """并行处理一批仓库"""
    global running
    
    print(f"\n🚀 并行处理 {len(repos)} 条 (并发: {MAX_WORKERS})")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_single_repo, db_path, repo): repo 
            for repo in repos
        }
        
        for future in as_completed(futures):
            if not running:
                break
            
            repo = futures[future]
            try:
                success = future.result()
                status = "✅" if success else "❌"
                print(f"  {status} {repo['name'][:40]} ({repo['stars']}⭐)")
            except Exception as e:
                print(f"  ❌ {repo['name'][:40]} - Error: {e}")

def get_pending_count(db_path):
    """获取待标注数量"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM rosclaw_hub_resources
        WHERE is_relevant = 1
        AND (llm_model IS NULL OR llm_model != ?)
    """, (MODEL,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def main():
    """主函数"""
    global running
    
    print("=" * 70)
    print("🤖 ROSClaw LLM Parallel Annotation (5 Workers)")
    print("=" * 70)
    print(f"🤖 Model: {MODEL}")
    print(f"⚡ Concurrency: {MAX_WORKERS}")
    print("=" * 70)
    
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'rosclaw_hub.db'
    
    pending = get_pending_count(db_path)
    print(f"\n📊 待标注: {pending} 条")
    print(f"⚡ 预估速度: ~{MAX_WORKERS}条/分钟")
    print(f"⏱️  预估完成: ~{pending / MAX_WORKERS / 60:.1f} 小时\n")
    
    batch_num = 0
    
    while running and get_pending_count(db_path) > 0:
        batch_num += 1
        repos = get_pending_repos(db_path, batch_size=MAX_WORKERS * 2)
        
        if not repos:
            break
        
        process_batch_parallel(db_path, repos)
        
        # 批次间短暂休息
        time.sleep(2)
    
    # 最终统计
    print("\n" + "=" * 70)
    print("📊 最终统计")
    print("=" * 70)
    print(f"  总处理: {stats['total']}")
    print(f"  ✅ 成功: {stats['success']}")
    print(f"  ❌ 失败: {stats['failed']}")
    print(f"  🏆 高相关(80+): {stats['high_score']}")
    print(f"  📊 中相关(50-79): {stats['medium_score']}")
    print(f"  📉 低相关(0-49): {stats['low_score']}")
    print("=" * 70)

if __name__ == '__main__':
    main()
