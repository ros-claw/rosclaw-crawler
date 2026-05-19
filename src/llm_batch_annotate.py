#!/usr/bin/env python3
"""
ROSClaw LLM Batch Re-Annotation Pipeline
使用阿里百炼 Qwen3.5-plus 重新标注全部数据
"""

import json
import sqlite3
import requests
from datetime import datetime
import time
import sys
import signal

API_KEY = ""${DEEPSEEK_API_KEY}""
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.5-plus"

# 统计
stats = {
    'total': 0,
    'success': 0,
    'failed': 0,
    'high_score': 0,  # 80-100
    'medium_score': 0,  # 50-79
    'low_score': 0     # 0-49
}

running = True

def signal_handler(sig, frame):
    global running
    print("\n🛑 收到停止信号，正在保存进度...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def create_prompt(repo_type, name, description, url, stars):
    """创建标注Prompt"""
    
    if repo_type == 'mcp_server':
        template = "MCP Server Analysis: focus on physical/simulation capabilities, robot control, MCP tools, ROS/Isaac/MuJoCo integration."
    else:
        template = "Agent Skill Analysis: focus on physical tasks, robot types, actions/capabilities, cross-platform use."
    
    desc = description or "No description provided"
    
    prompt = """You are an expert evaluator for the ROSClaw Physical AI Ecosystem.
Mission: "Teach Once, Embody Anywhere. Share Skills, Shape Reality."

Repository: %s
Type: %s  
URL: %s
Stars: %d
Description: %s

%s

Key concepts for ROSClaw (HIGHER relevance if matching):
- Embodied AI, Physical AI, Robotics, Humanoid robots
- ROS/ROS2, DDS middleware
- VLA (Vision-Language-Action), VLN (Vision-Language Navigation), World Models
- Isaac Sim, MuJoCo, Gazebo, PyBullet, Sim-to-Real
- Manipulation, Navigation, Control, Perception
- SLAM, 3D Reconstruction, NeRF, 3DGS, Sensor Fusion
- Reinforcement Learning, Imitation Learning, ACT, Diffusion Policy
- Robot hardware: RealSense, LiDAR, Jetson, Raspberry Pi, sensors, motors
- IoT for robotics, Smart Manufacturing, Industrial Automation
- Kinematics, Dynamics, MPC, WBC

SCORING (STRICT for ROSClaw ecosystem):
- 90-100: DIRECT embodied AI (robot manipulation, navigation, control, perception with real/sim robots, VLA/VLN models)
- 80-89: STRONGLY related - IoT for robotics, robot hardware (RealSense, robot bodies), robot algorithms, ROS tools, Isaac/MuJoCo/Gazebo
- 70-79: Robot learning frameworks (RL for robots, imitation learning), hardware drivers, sim-to-real
- 50-69: Moderately related - CV/ML tools usable for robots, 3D vision
- 30-49: Weakly related - General AI/LLM tools that could theoretically apply
- 0-29: NOT relevant - Web apps, document tools, general software

Provide JSON:
{
  "summary": "What this project does (2-3 sentences)",
  "relevance_score": 0-100,
  "category": "Primary category",
  "subcategory": "More specific",
  "robot_types": ["Robot types or 'None'"],
  "tags": ["5-10 tags"],
  "capabilities": ["Key functions"],
  "mcp_tools": null or [{"name": "x", "description": "y"}],
  "hardware_requirements": [],
  "software_dependencies": [],
  "is_rosclaw_native": true/false,
  "confidence": 0-100
}

Return ONLY valid JSON.""" % (name, repo_type, url, stars, desc, template)
    
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
            {"role": "system", "content": "You are a robotics and embodied AI expert."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 1500
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(
                BASE_URL + "/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                
                # 清理markdown代码块
                content = content.strip()
                if content.startswith("```json"):
                    content = content[7:]
                elif content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                
                return json.loads(content)
                
            elif response.status_code == 401:
                print("  ❌ API 401错误: Token无效或过期")
                return None
            elif response.status_code == 429:
                print("  ⚠️ API限流，等待30秒...")
                time.sleep(30)
                continue
            else:
                print("  ⚠️ API错误 %d: %s" % (response.status_code, response.text[:100]))
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))
                    
        except json.JSONDecodeError as e:
            print("  ⚠️ JSON解析失败: %s" % str(e))
            return None
        except Exception as e:
            print("  ⚠️ 请求错误: %s" % str(e))
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))
    
    return None

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

def get_pending_repos(db_path, batch_size=10):
    """获取一批待标注仓库"""
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

def update_repo(db_path, repo_id, result, max_retries=5):
    """更新数据库，带重试机制"""
    
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
    
    for attempt in range(max_retries):
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
            
        except sqlite3.OperationalError as e:
            if 'database is locked' in str(e) and attempt < max_retries - 1:
                print("    ⏳ 数据库锁定，等待 %d 秒..." % (2 * (attempt + 1)))
                time.sleep(2 * (attempt + 1))
                continue
            else:
                raise
    
    return None

def process_db(db_path):
    """处理单个数据库"""
    global stats, running
    
    print("\n" + "=" * 70)
    print("📁 处理数据库: %s" % db_path)
    print("=" * 70)
    
    pending = get_pending_count(db_path)
    print("待标注记录: %d 条\n" % pending)
    
    if pending == 0:
        print("✅ 所有记录已标注完成")
        return
    
    batch_num = 0
    
    while running:
        repos = get_pending_repos(db_path, 5)  # 每批5条
        
        if not repos:
            print("✅ 数据库 %s 标注完成!" % db_path)
            break
        
        batch_num += 1
        print("📦 批次 #%d | 本批 %d 条 | 累计: %d成功 %d失败" % 
              (batch_num, len(repos), stats['success'], stats['failed']))
        
        for i, repo in enumerate(repos, 1):
            if not running:
                break
                
            print("  [%d/%d] %s (%d⭐)" % (i, len(repos), repo['name'][:40], repo['stars']))
            
            prompt = create_prompt(
                repo['type'], repo['name'], repo['description'],
                repo['repo_url'], repo['stars']
            )
            
            result = call_llm(prompt)
            
            if result:
                score = update_repo(db_path, repo['id'], result)
                stats['success'] += 1
                stats['total'] += 1
                
                if score >= 80:
                    stats['high_score'] += 1
                elif score >= 50:
                    stats['medium_score'] += 1
                else:
                    stats['low_score'] += 1
                    
                print("    ✅ Score: %d | Category: %s | ROSClaw: %s" % (
                    score, 
                    result.get('category', '?')[:20],
                    '✓' if result.get('is_rosclaw_native') or score >= 70 else '✗'
                ))
            else:
                stats['failed'] += 1
                stats['total'] += 1
                print("    ❌ 标注失败")
            
            time.sleep(1)  # 请求间隔
        
        if not running:
            break
            
        print("  ⏳ 批次完成，休息3秒...\n")
        time.sleep(3)

def main():
    """主函数"""
    print("=" * 70)
    print("🤖 ROSClaw LLM Batch Re-Annotation Pipeline")
    print("=" * 70)
    print("🤖 模型: %s" % MODEL)
    print("🌐 API: 阿里百炼 Bailian")
    print("🎯 评分标准:")
    print("   90-100: 直接具身AI实现")
    print("   80-89: 强相关 - IoT/机器人硬件/算法/ROS/仿真平台")
    print("   70-79: 机器人学习框架/驱动/ Sim-to-Real")
    print("   50-69: 中等相关 - CV/ML工具")
    print("   0-49: 弱相关/不相关")
    print("=" * 70)
    
    # 处理所有数据库
    databases = ['rosclaw_hub.db', 'rosclaw_hub_crawler.db']
    
    for db in databases:
        if get_pending_count(db) > 0:
            process_db(db)
        else:
            print("\n✅ %s 已完全标注" % db)
    
    # 最终统计
    print("\n" + "=" * 70)
    print("📊 最终统计")
    print("=" * 70)
    print("  总处理: %d" % stats['total'])
    print("  ✅ 成功: %d (%.1f%%)" % (stats['success'], stats['success']*100/max(stats['total'],1)))
    print("  ❌ 失败: %d" % stats['failed'])
    print("  🏆 高相关(80+): %d" % stats['high_score'])
    print("  📊 中相关(50-79): %d" % stats['medium_score'])
    print("  📉 低相关(0-49): %d" % stats['low_score'])
    print("=" * 70)

if __name__ == '__main__':
    main()
