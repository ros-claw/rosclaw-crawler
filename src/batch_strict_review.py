#!/usr/bin/env python3
"""
批量严格审核 - 先规则过滤，再LLM审核边界项目
"""

import sqlite3
import json
import time
import requests
import re
from datetime import datetime

DB_PATH = '/home/ubuntu/.openclaw/workspace/rosclaw_crawler/rosclaw_hub.db'
API_KEY = '"${ROSCALW_API_KEY}"'
BASE_URL = 'https://www.rosclaw.io'
MCP_ENDPOINT = f'{BASE_URL}/api/mcp-packages'
SKILL_ENDPOINT = f'{BASE_URL}/api/skills'

DEEPSEEK_API_KEY = '"${DEEPSEEK_API_KEY}"'
DEEPSEEK_BASE_URL = 'https://api.deepseek.com'
DEEPSEEK_MODEL = 'deepseek-v4-pro'

HEADERS = {
    'Content-Type': 'application/json',
    'X-API-Key': API_KEY
}

# 硬性排除规则
SKIP_PATTERNS = [
    r'awesome[-_]', r'curated', r'hub$', r'-hub$', r'_hub$',
    r'mcp-hub', r'skill-hub', r'/skills$', r'\.github\.io',
    r'dotfiles', r'config$', r'configs$', r'personal-blog',
    r'benchmark', r'dataset', r'foundation-model',
]

# 明确接受的MCP关键词
MCP_ACCEPT_PATTERNS = [
    r'mcp[-_]?server', r'mcp[-_]?ros', r'ros[-_]?mcp',
    r'@modelcontextprotocol', r'mcp[-_]?sdk',
]

# 明确接受的Skill关键词  
SKILL_ACCEPT_PATTERNS = [
    r'ros2?[-_]?node', r'robot[-_]?control', r'manipulation',
    r'navigation2?', r'grasp', r'locomotion', r'quadruped',
    r'humanoid', r'arm[-_]?control', r'teleoperation',
]

# 明确排除的仿真/框架关键词
SKIP_SIMULATION = [
    r'gymnasium', r'gym[-_]?env', r'sim[-_]?env', r'simulation[-_]?platform',
    r'isaac[-_]?sim', r'mujoco[-_]?env', r'pybullet[-_]?env',
    r'benchmark', r'dataset[-_]?collection',
]

def is_valid_github_url(url):
    if not url:
        return False
    pattern = r'^https://github\.com/[^/]+/[^/]+$'
    return bool(re.match(pattern, url))

def quick_classify(repo_url, name, description, llm_summary):
    """快速分类：accept_mcp, accept_skill, skip, need_llm"""
    text = f"{name} {description} {llm_summary}".lower()
    url_name = f"{repo_url} {name}".lower()
    
    # 硬性排除
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, url_name):
            return 'skip', f'Pattern: {pattern}'
    
    # 排除仿真平台
    for pattern in SKIP_SIMULATION:
        if re.search(pattern, text):
            return 'skip', f'Simulation: {pattern}'
    
    # 检查是否是openclaw skills子目录
    if 'openclaw/skills/tree' in repo_url:
        return 'skip', 'OpenClaw skills subtree'
    
    # 明确接受MCP
    for pattern in MCP_ACCEPT_PATTERNS:
        if re.search(pattern, text):
            return 'accept_mcp', f'MCP pattern: {pattern}'
    
    # 明确接受Skill
    for pattern in SKILL_ACCEPT_PATTERNS:
        if re.search(pattern, text):
            return 'accept_skill', f'Skill pattern: {pattern}'
    
    # 边界情况需要LLM审核
    return 'need_llm', ''

def strict_llm_review_batch(items):
    """批量LLM审核"""
    # 构建批量prompt
    items_text = []
    for i, item in enumerate(items):
        items_text.append(f"""
项目{i+1}:
- ID: {item['id']}
- 名称: {item['name']}
- URL: {item['repo_url']}
- 描述: {item.get('description', '')}
- LLM摘要: {item.get('llm_summary', '')}
""")
    
    prompt = f"""你是一个严格的ROSClaw项目审核专家。ROSClaw是具身智能（Embodied AI）平台，只接受：
1. MCP服务器：真正实现MCP协议，有明确的tools/capabilities列表，有server实现代码
2. Skill：具体机器人技能，有实际的ROS2/ROS1节点或物理交互控制代码

必须拒绝：
- 纯AI模型/预训练权重（没有物理交互代码）
- 仿真平台/环境（如Maniskill是仿真平台，不是skill）
- 数据集/benchmark
- 只有概念描述，没有实际代码
- 名字带"skill"但实际不是机器人技能

对以下每个项目，输出一行JSON：
{{"id": 项目ID, "type": "mcp|skill|skip", "confidence": 0-100, "reason": "原因"}}

{''.join(items_text)}

只输出JSON数组，不要其他文字。"""
    
    try:
        response = requests.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={
                'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json'
            },
            json={
                'model': DEEPSEEK_MODEL,
                'messages': [
                    {'role': 'system', 'content': 'You are a strict project reviewer. Only accept real MCP servers or robot skills with ROS/physical control code. Output JSON array only.'},
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': 0.1,
                'max_tokens': 2000
            },
            timeout=120
        )
        
        if response.status_code != 200:
            print(f"  LLM API error: HTTP {response.status_code}")
            return []
        
        result = response.json()
        content = result['choices'][0]['message']['content']
        
        # 清理
        content = content.strip()
        if content.startswith('```json'):
            content = content[7:]
        if content.startswith('```'):
            content = content[3:]
        if content.endswith('```'):
            content = content[:-3]
        content = content.strip()
        
        try:
            reviews = json.loads(content)
            return reviews if isinstance(reviews, list) else []
        except:
            # 尝试逐行解析
            reviews = []
            for line in content.split('\n'):
                line = line.strip()
                if line and line.startswith('{'):
                    try:
                        reviews.append(json.loads(line))
                    except:
                        pass
            return reviews
            
    except Exception as e:
        print(f"  LLM batch error: {e}")
        return []

def get_all_candidates():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, repo_url, name, description, stars, 
               llm_relevance_score, llm_summary, llm_category,
               llm_key_features, llm_analyzed_at, llm_model
        FROM rosclaw_hub_resources
        WHERE llm_relevance_score >= 70
          AND (llm_upload_status IS NULL OR llm_upload_status != 'uploaded')
        ORDER BY llm_relevance_score DESC, stars DESC
    """)
    
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items

def update_status(item_id, status, upload_type, reason):
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE rosclaw_hub_resources 
            SET llm_upload_status = ?,
                llm_upload_type = ?,
                llm_upload_reason = ?
            WHERE id = ?
        """, (status, upload_type, reason, item_id))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"    DB error: {e}")
        return False

def main():
    start_time = time.time()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    print("=" * 70)
    print("ROSClaw 批量严格审核")
    print("=" * 70)
    
    candidates = get_all_candidates()
    total = len(candidates)
    print(f"\n候选项目: {total}")
    
    # 第一阶段：快速规则分类
    accept_mcp = []
    accept_skill = []
    skip_items = []
    need_llm = []
    
    print("\n第一阶段：规则快速分类...")
    for item in candidates:
        result, reason = quick_classify(
            item['repo_url'], 
            item.get('name', ''), 
            item.get('description', ''), 
            item.get('llm_summary', '')
        )
        
        if result == 'accept_mcp':
            accept_mcp.append(item)
        elif result == 'accept_skill':
            accept_skill.append(item)
        elif result == 'skip':
            skip_items.append((item, reason))
        else:
            need_llm.append(item)
    
    print(f"  规则接受MCP: {len(accept_mcp)}")
    print(f"  规则接受Skill: {len(accept_skill)}")
    print(f"  规则跳过: {len(skip_items)}")
    print(f"  需要LLM: {len(need_llm)}")
    
    # 更新规则分类结果
    print("\n更新规则分类结果...")
    for item in accept_mcp:
        update_status(item['id'], 'pending_api', 'mcp', 'Rule accepted: MCP pattern')
    for item in accept_skill:
        update_status(item['id'], 'pending_api', 'skill', 'Rule accepted: Skill pattern')
    for item, reason in skip_items:
        update_status(item['id'], 'skipped', None, f'Rule skipped: {reason}')
    
    # 第二阶段：LLM批量审核边界项目
    print(f"\n第二阶段：LLM批量审核 {len(need_llm)} 个项目...")
    
    batch_size = 10
    llm_accepted = 0
    llm_skipped = 0
    
    for i in range(0, len(need_llm), batch_size):
        batch = need_llm[i:i+batch_size]
        print(f"\n  LLM审核批次 {i//batch_size + 1}/{(len(need_llm)-1)//batch_size + 1} ({len(batch)}个项目)")
        
        reviews = strict_llm_review_batch(batch)
        
        # 匹配审核结果
        review_map = {}
        for review in reviews:
            review_map[review.get('id')] = review
        
        for item in batch:
            item_id = item['id']
            review = review_map.get(item_id, {})
            
            review_type = review.get('type', 'skip')
            confidence = review.get('confidence', 0)
            reason = review.get('reason', 'No review')
            
            if confidence < 80 or review_type == 'skip':
                update_status(item_id, 'skipped', None, f'LLM: {reason}')
                llm_skipped += 1
                print(f"    ⏭️ {item.get('name')} - skip ({confidence})")
            else:
                update_status(item_id, 'pending_api', review_type, f'LLM: {reason}')
                llm_accepted += 1
                print(f"    ✅ {item.get('name')} - {review_type} ({confidence})")
        
        time.sleep(1)
    
    # 统计
    elapsed = time.time() - start_time
    
    print("\n" + "=" * 70)
    print("审核完成!")
    print("=" * 70)
    print(f"总计候选: {total}")
    print(f"规则接受MCP: {len(accept_mcp)}")
    print(f"规则接受Skill: {len(accept_skill)}")
    print(f"规则跳过: {len(skip_items)}")
    print(f"LLM接受: {llm_accepted}")
    print(f"LLM跳过: {llm_skipped}")
    print(f"总计接受: {len(accept_mcp) + len(accept_skill) + llm_accepted}")
    print(f"耗时: {elapsed:.2f}秒")

if __name__ == '__main__':
    main()
