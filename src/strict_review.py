#!/usr/bin/env python3
"""
严格LLM审核规则 - 重新处理ROSClaw项目

硬性门槛：
1. 必须是GitHub项目：https://github.com/owner/repo
2. 不能是：awesome-list, hub, 纯文档, 个人博客
3. 不能重复：owner/repo唯一

MCP vs Skill严格区分：
- MCP：真正实现MCP协议，有tools列表
- Skill：具体机器人技能，有ROS节点或物理控制代码

审核标准：
- 拒绝：纯AI模型、仿真平台、数据集、工具库、框架
- 拒绝：只有概念描述，没有实际代码
- 拒绝：名字误导（如Maniskill是仿真平台，不是skill）
- 接受：必须有明确的物理交互或MCP工具实现

confidence < 80 标记为skip
"""

import sqlite3
import json
import time
import requests
import re
from datetime import datetime
from urllib.parse import urlparse

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

# 硬性过滤规则 - 直接排除
SKIP_PATTERNS = [
    r'awesome-',
    r'awesome_',
    r'curated',
    r'hub$',
    r'-hub$',
    r'_hub$',
    r'mcp-hub',
    r'skill-hub',
    r'/skills$',
    r'\.github\.io',
    r'personal-blog',
    r'dotfiles',
    r'config$',
    r'configs$',
]

# 仿真平台/数据集/纯模型 - 需要LLM识别
SIMULATION_KEYWORDS = [
    'simulation platform', '仿真平台', 'benchmark', '数据集', 'dataset',
    'foundation model', 'pre-trained', 'weights', 'checkpoint',
    'gymnasium', 'gym environment', 'rl environment',
]

def is_valid_github_url(url):
    """检查是否是有效的GitHub项目URL"""
    if not url:
        return False
    pattern = r'^https://github\.com/[^/]+/[^/]+$'
    return bool(re.match(pattern, url))

def should_skip_by_pattern(repo_url, name):
    """基于硬性规则判断是否跳过"""
    url_lower = repo_url.lower()
    name_lower = name.lower() if name else ''
    
    # 检查skip patterns
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, url_lower) or re.search(pattern, name_lower):
            return True, f"Pattern match: {pattern}"
    
    # 检查是否是openclaw/skills (skill hub)
    if 'openclaw/skills' in url_lower:
        return True, "Skill hub"
    
    # 检查awesome列表
    if 'awesome' in name_lower and ('list' in name_lower or 'skill' in name_lower or 'mcp' in name_lower):
        return True, "Awesome list"
    
    return False, ""

def get_all_candidates():
    """获取所有候选项目（分数>=70）"""
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

def strict_llm_review(item):
    """使用严格规则进行LLM审核"""
    repo_url = item['repo_url']
    name = item.get('name', '')
    description = item.get('description', '')
    llm_summary = item.get('llm_summary', '')
    
    # 硬性过滤
    should_skip, reason = should_skip_by_pattern(repo_url, name)
    if should_skip:
        return {
            "type": "skip",
            "reason": f"Hard filter: {reason}",
            "category": "filtered",
            "robot_types": [],
            "confidence": 0
        }
    
    # 构建prompt
    prompt = f"""你是一个严格的ROSClaw项目审核专家。ROSClaw是具身智能（Embodied AI）平台，只接受：
1. MCP服务器：真正实现MCP协议，有明确的tools/capabilities列表，有server实现代码
2. Skill：具体机器人技能，有实际的ROS2/ROS1节点或物理交互控制代码

必须拒绝以下类型：
- awesome-list / curated-list / 列表集合
- hub / skill-hub / mcp-hub
- 纯文档/教程/学习项目
- 个人博客/配置仓库
- 纯AI模型/预训练权重（没有物理交互代码）
- 仿真平台/环境（如Maniskill是仿真平台，不是skill）
- 数据集/benchmark
- 只有概念描述，没有实际代码
- 名字带"skill"但实际不是机器人技能（如coding skill, writing skill）

项目信息：
- 名称: {name}
- URL: {repo_url}
- 描述: {description}
- LLM摘要: {llm_summary}

审核要求：
- MCP必须明确实现MCP SDK（@modelcontextprotocol依赖），提供具体tools列表
- Skill必须有ROS节点代码或物理控制代码（不是仿真环境）
- 拒绝"支持MCP"或"兼容MCP"但没有实际server实现的项目
- 拒绝只有README描述没有代码的项目

输出JSON格式：
{{
  "type": "mcp" | "skill" | "skip",
  "reason": "详细原因（为什么接受或拒绝）",
  "category": "具体分类",
  "robot_types": ["支持的机器人类型"],
  "confidence": 0-100
}}

如果confidence < 80，type必须是"skip"
"""
    
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
                    {'role': 'system', 'content': 'You are a strict project reviewer for an Embodied AI platform. Only accept real MCP servers with tool implementations or real robot skills with ROS/physical control code. Be very conservative. Always respond with valid JSON only.'},
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': 0.1,
                'max_tokens': 800
            },
            timeout=60
        )
        
        if response.status_code != 200:
            return {
                "type": "skip",
                "reason": f"LLM API error: HTTP {response.status_code}",
                "category": "error",
                "robot_types": [],
                "confidence": 0
            }
        
        result = response.json()
        content = result['choices'][0]['message']['content']
        
        # 清理可能的markdown代码块
        content = content.strip()
        if content.startswith('```json'):
            content = content[7:]
        if content.startswith('```'):
            content = content[3:]
        if content.endswith('```'):
            content = content[:-3]
        content = content.strip()
        
        try:
            review = json.loads(content)
        except json.JSONDecodeError:
            # 尝试提取JSON部分
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                review = json.loads(json_match.group())
            else:
                raise
        
        # 确保confidence < 80时标记为skip
        if review.get('confidence', 0) < 80:
            review['type'] = 'skip'
        
        return review
        
    except Exception as e:
        return {
            "type": "skip",
            "reason": f"LLM review error: {str(e)[:100]}",
            "category": "error",
            "robot_types": [],
            "confidence": 0
        }

def update_review_status(item_id, review, original_item):
    """更新数据库审核状态"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        cursor = conn.cursor()
        
        review_type = review.get('type', 'skip')
        confidence = review.get('confidence', 0)
        
        if review_type == 'skip':
            status = 'skipped'
        else:
            status = 'pending_api'
        
        cursor.execute("""
            UPDATE rosclaw_hub_resources 
            SET llm_upload_status = ?,
                llm_upload_type = ?,
                llm_upload_category = ?,
                llm_upload_reason = ?,
                llm_upload_tags = ?,
                llm_upload_robot_type = ?
            WHERE id = ?
        """, (
            status,
            review_type if review_type != 'skip' else None,
            review.get('category'),
            review.get('reason'),
            json.dumps(review.get('robot_types', [])),
            json.dumps(review.get('robot_types', [])),
            item_id
        ))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"    ⚠️ 数据库更新失败: {e}")
        return False

def main():
    start_time = time.time()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    print("=" * 70)
    print("ROSClaw 严格LLM审核工具")
    print("=" * 70)
    
    # 获取候选项目
    candidates = get_all_candidates()
    total = len(candidates)
    print(f"\n候选项目总数 (score>=70): {total}")
    
    if total == 0:
        print("没有候选项目，退出")
        return
    
    # 统计
    stats = {
        'total': total,
        'hard_filtered': 0,
        'mcp_accepted': 0,
        'skill_accepted': 0,
        'skipped': 0,
        'error': 0
    }
    
    results = []
    
    for i, item in enumerate(candidates, 1):
        item_id = item['id']
        name = item.get('name', 'unknown')
        repo_url = item['repo_url']
        
        print(f"\n[{i}/{total}] 审核: {name}")
        print(f"  URL: {repo_url}")
        
        # 硬性过滤
        should_skip, reason = should_skip_by_pattern(repo_url, name)
        if should_skip:
            print(f"  ⏭️ 硬性过滤: {reason}")
            stats['hard_filtered'] += 1
            
            review = {
                "type": "skip",
                "reason": f"Hard filter: {reason}",
                "category": "filtered",
                "robot_types": [],
                "confidence": 0
            }
            update_review_status(item_id, review, item)
            
            results.append({
                'id': item_id,
                'name': name,
                'result': 'hard_filtered',
                'reason': reason
            })
            continue
        
        # LLM严格审核
        print(f"  🤖 LLM审核中...")
        review = strict_llm_review(item)
        
        review_type = review.get('type', 'skip')
        confidence = review.get('confidence', 0)
        reason = review.get('reason', '')
        
        print(f"  结果: {review_type} (confidence={confidence})")
        print(f"  原因: {reason[:100]}...")
        
        # 更新状态
        update_review_status(item_id, review, item)
        
        if review_type == 'mcp':
            stats['mcp_accepted'] += 1
            print(f"  ✅ MCP接受")
        elif review_type == 'skill':
            stats['skill_accepted'] += 1
            print(f"  ✅ Skill接受")
        else:
            stats['skipped'] += 1
            print(f"  ⏭️ 跳过")
        
        results.append({
            'id': item_id,
            'name': name,
            'result': review_type,
            'confidence': confidence,
            'reason': reason
        })
        
        # 速率控制
        if i % 10 == 0:
            print(f"\n  ⏳ 已处理 {i}/{total}，暂停2秒...")
            time.sleep(2)
        else:
            time.sleep(0.5)
    
    # 计算耗时
    elapsed = time.time() - start_time
    
    # 生成日志
    log_data = {
        'timestamp': timestamp,
        'stats': stats,
        'elapsed_seconds': round(elapsed, 2),
        'results': results
    }
    
    log_filename = f'/home/ubuntu/.openclaw/workspace/rosclaw_crawler/strict_review_{timestamp}.json'
    with open(log_filename, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    
    # 输出统计
    print("\n" + "=" * 70)
    print("审核完成!")
    print("=" * 70)
    print(f"总计: {stats['total']}")
    print(f"硬性过滤: {stats['hard_filtered']}")
    print(f"MCP接受: {stats['mcp_accepted']}")
    print(f"Skill接受: {stats['skill_accepted']}")
    print(f"跳过: {stats['skipped']}")
    print(f"错误: {stats['error']}")
    print(f"耗时: {elapsed:.2f}秒")
    print(f"日志文件: {log_filename}")
    
    return log_data

if __name__ == '__main__':
    main()
