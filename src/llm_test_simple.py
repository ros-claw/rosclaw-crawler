#!/usr/bin/env python3
"""
ROSClaw LLM Re-Annotation Pipeline - Simplified Version
使用阿里百炼 Qwen3.5-plus 重新标注所有数据
"""

import json
import sqlite3
import requests
from datetime import datetime
import time

API_KEY = "BAILIAN_KEY_PLACEHOLDER"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.5-plus"

def create_prompt(repo_type, name, description, url, stars):
    """创建标注Prompt - 使用普通字符串避免f-string问题"""
    
    if repo_type == 'mcp_server':
        template = "MCP Server Analysis: focus on physical/simulation capabilities, robot control, MCP tools, ROS/Isaac Sim integration."
    else:
        template = "Agent Skill Analysis: focus on physical tasks, robot types, actions/capabilities, cross-platform use."
    
    prompt = """You are an expert evaluator for the ROSClaw Physical AI Ecosystem.
Mission: "Teach Once, Embody Anywhere. Share Skills, Shape Reality."

Repository: %s
Type: %s
URL: %s
Stars: %d
Description: %s

%s

Key concepts for high relevance: Embodied AI, Physical AI, Robotics, ROS/ROS2, 
VLA (Vision-Language-Action), VLN (Vision-Language Navigation), World Models,
Isaac Sim, MuJoCo, Gazebo, SLAM, 3D Reconstruction, Manipulation, Navigation,
Reinforcement Learning, Imitation Learning, Sim-to-Real, Digital Twin.

Provide JSON with these fields:
- summary (string): What this project does
- relevance_score (0-100): How relevant to ROSClaw ecosystem
- category (string): e.g., Manipulation, Navigation, Perception, Simulation, Control, General
- subcategory (string): More specific type
- robot_types (array): Supported robot types or ["None"]
- tags (array): 5-10 relevant tags
- capabilities (array): Key functions provided
- mcp_tools (array or null): For MCP servers, list tools
- hardware_requirements (array): Required hardware or empty
- software_dependencies (array): Key deps like ROS, ROS2, PyTorch
- is_rosclaw_native (boolean): Can it work with ROSClaw directly
- confidence (0-100): Your confidence in this analysis

Scoring guidelines (STRICT - for ROSClaw Physical AI Ecosystem):
- 90-100: DIRECT embodied AI implementations (robot manipulation, navigation, control, perception with real/sim robots, VLA/VLN models)
- 80-89: STRONGLY related - IoT for robotics, robot hardware (sensors like RealSense, robot bodies), robot algorithms, ROS/ROS2 tools, Isaac Sim/MuJoCo/Gazebo
- 70-79: Robot learning frameworks (RL for robots, imitation learning), hardware drivers, sim-to-real tools
- 50-69: Moderately related - CV/ML tools usable for robots, 3D vision, SLAM-adjacent tools
- 30-49: Weakly related - General AI/LLM tools that could theoretically apply to robotics
- 0-29: NOT relevant - Web apps, document tools, general software (e.g., markitdown, weather APIs, stock tools)

Return ONLY valid JSON.""" % (name, repo_type, url, stars, description or "No description", template)
    
    return prompt

def call_llm(prompt):
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
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            return json.loads(content)
        else:
            print("API Error %d: %s" % (response.status_code, response.text[:200]))
            return None
            
    except Exception as e:
        print("Request error: %s" % str(e))
        return None

def get_repos(db_path, limit=5):
    """获取需要标注的仓库"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, type, repo_url, name, description, stars
        FROM rosclaw_hub_resources
        WHERE is_relevant = 1
        AND (llm_model IS NULL OR llm_model != ?)
        ORDER BY stars DESC
        LIMIT ?
    """, (MODEL, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [{
        'id': r[0], 'type': r[1], 'repo_url': r[2], 
        'name': r[3], 'description': r[4], 'stars': r[5]
    } for r in rows]

def update_repo(db_path, repo_id, result):
    """更新数据库"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
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
        result.get('relevance_score', 0),
        result.get('category', 'Unknown'),
        json.dumps(features, ensure_ascii=False),
        datetime.now().isoformat(),
        MODEL,
        json.dumps(result.get('tags', []), ensure_ascii=False),
        result.get('is_rosclaw_native', False) or result.get('relevance_score', 0) >= 70,
        repo_id
    ))
    
    conn.commit()
    conn.close()

def run_test(db_path='rosclaw_hub.db', count=5):
    """运行小规模测试"""
    print("=" * 70)
    print("ROSClaw LLM Re-Annotation Test")
    print("Model: %s | API: Bailian" % MODEL)
    print("=" * 70)
    
    repos = get_repos(db_path, count)
    
    if not repos:
        print("No repositories need annotation.")
        return
    
    print("\nFound %d repositories to annotate\n" % len(repos))
    
    for i, repo in enumerate(repos, 1):
        print("[%d/%d] %s (%d stars)" % (i, len(repos), repo['name'], repo['stars']))
        print("URL: %s" % repo['repo_url'])
        
        prompt = create_prompt(
            repo['type'], repo['name'], repo['description'],
            repo['repo_url'], repo['stars']
        )
        
        result = call_llm(prompt)
        
        if result:
            update_repo(db_path, repo['id'], result)
            print("✅ Score: %d/100 | Category: %s" % (
                result.get('relevance_score', 0),
                result.get('category', 'Unknown')
            ))
            print("   Tags: %s" % ', '.join(result.get('tags', [])[:5]))
            print("   Robot Types: %s" % ', '.join(result.get('robot_types', [])[:3]))
            print("   ROSClaw Native: %s\n" % result.get('is_rosclaw_native', False))
        else:
            print("❌ Failed to annotate\n")
        
        time.sleep(1)  # Rate limiting
    
    print("=" * 70)
    print("Test completed!")
    print("=" * 70)

if __name__ == '__main__':
    import sys
    db = sys.argv[1] if len(sys.argv) > 1 else 'rosclaw_hub.db'
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    run_test(db, count)
