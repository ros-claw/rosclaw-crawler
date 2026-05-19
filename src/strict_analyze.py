#!/usr/bin/env python3
"""
ROSClaw 严格分析模块
使用DeepSeek V4 Pro对全库进行三重条件审核
输出可上传清单（本地确认）
"""
import sqlite3
import json
import urllib.request
from datetime import datetime, timezone
import os

DB_PATH = '/home/ubuntu/.openclaw/workspace/rosclaw_crawler/rosclaw_hub.db'

# DeepSeek V4 Pro
API_KEY = 'os.getenv("DEEPSEEK_API_KEY", "")'
API_URL = 'https://api.deepseek.com/v1/chat/completions'
MODEL = 'deepseek-v4-pro'

STRICT_PROMPT_TEMPLATE = """你是一名严格的AI资源审核员，为rosclaw.io（Physical AI生态平台）筛选项目。

## 必须同时满足的三个条件（AND关系）：

### 条件1：明确类型
必须是以下之一：
- **MCP Server**: 实现了Model Context Protocol，为AI Agent提供工具/资源
- **Agent Skill**: 为AI Agent设计的技能/工具包，可直接被Agent调用执行物理任务

### 条件2：Agent相关性
必须与以下概念直接相关：
AI Agent、多智能体(Multi-Agent)、OpenClaw、Claude Code、Autonomous Agent、Agent Framework、Agent Skill、MCP

### 条件3：具身智能相关性
必须与具身智能(Embodied AI)/Physical AI/机器人/ROS相关，涉及：
机器人控制、导航、操作、仿真、感知、运动规划、传感器、ROS/ROS2等

## 明确拒绝（只要满足一项就拒绝）：
- 纯软件工具（不含物理交互）
- 办公/文档/营销类
- 教程/列表/合集
- 纯AI聊天/助手（不含机器人）
- 通用开发工具/框架（不含Agent接口）

---

待审核项目：
- 名称: {name}
- 描述: {description}
- URL: {url}
- Stars: {stars}

请严格按照以下JSON格式输出，不要添加任何解释：

{{
  "passed": true/false,
  "type": "mcp" 或 "skill" 或 "none",
  "reason": "通过/拒绝的具体原因，引用项目名称说明",
  "category": "control/navigation/manipulation/simulation/perception/planning/locomotion/general",
  "relevance_score": 1-10,
  "confidence": "high/medium/low",
  "agent_evidence": "项目中体现Agent/MCP/Skill的具体证据",
  "embodied_evidence": "项目中体现具身智能/机器人的具体证据"
}}

**关键判断规则**：
- 如果项目只是"机器人相关的GitHub仓库"但没有明确的Agent/MCP/Skill接口 → passed: false
- 如果项目是通用算法库（纯运动学、纯SLAM）→ passed: false
- 如果项目明确提供了Agent可调用的物理交互接口 → passed: true
- 如果项目明确实现了MCP协议且与机器人相关 → passed: true
- 如果项目是纯软件技能（如SEO、营销、文档处理）→ passed: false
"""

def get_unanalyzed_repos(batch_size=10, min_stars=50):
    """获取待审核的项目批次"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 优先审核定向抓取的新项目，然后是未分析的旧项目
    cursor.execute('''
        SELECT id, name, description, repo_url, stars, source_query
        FROM rosclaw_hub_resources
        WHERE (llm_analyzed_at IS NULL OR llm_model != 'deepseek-v4-pro')
          AND stars >= ?
        ORDER BY 
            CASE WHEN source_query IS NOT NULL THEN 0 ELSE 1 END,
            stars DESC
        LIMIT ?
    ''', (min_stars, batch_size))
    
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def call_deepseek(repo_data):
    """调用DeepSeek V4 Pro进行严格审核"""
    prompt = STRICT_PROMPT_TEMPLATE.format(
        name=repo_data['name'],
        description=repo_data.get('description', 'N/A'),
        url=repo_data.get('repo_url', 'N/A'),
        stars=repo_data.get('stars', 0)
    )
    
    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a strict AI resource reviewer for Physical AI ecosystem."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }).encode('utf-8')
    
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            'Authorization': f'Bearer {API_KEY}',
            'Content-Type': 'application/json'
        },
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            return json.loads(content)
    except Exception as e:
        print(f"    API error: {e}")
        return None

def update_repo_analysis(repo_id, analysis):
    """保存分析结果到数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE rosclaw_hub_resources
        SET llm_relevance_score = ?,
            llm_category = ?,
            llm_summary = ?,
            llm_key_features = ?,
            llm_analyzed_at = ?,
            llm_model = ?
        WHERE id = ?
    ''', (
        analysis.get('relevance_score', 5),
        analysis.get('category', 'other'),
        analysis.get('reason', ''),
        json.dumps({
            'type': analysis.get('type'),
            'confidence': analysis.get('confidence'),
            'agent_evidence': analysis.get('agent_evidence'),
            'embodied_evidence': analysis.get('embodied_evidence')
        }, ensure_ascii=False),
        datetime.now(timezone.utc).isoformat(),
        'deepseek-v4-pro',
        repo_id
    ))
    
    conn.commit()
    conn.close()

def main():
    print("=" * 80)
    print("严格分析 - DeepSeek V4 Pro（全库审核）")
    print("=" * 80)
    
    # 获取待审核批次
    batch = get_unanalyzed_repos(batch_size=10, min_stars=50)
    print(f"\n本次审核: {len(batch)} 个项目\n")
    
    if not batch:
        print("没有待审核项目！")
        return
    
    passed_items = []
    rejected_items = []
    
    for i, repo in enumerate(batch, 1):
        print(f"[{i}/{len(batch)}] 审核: {repo['name']} (⭐ {repo.get('stars', 0)})")
        if repo.get('source_query'):
            print(f"    来源: 定向抓取 [{repo['source_query']}]")
        
        analysis = call_deepseek(repo)
        if analysis:
            # 保存到数据库
            update_repo_analysis(repo['id'], analysis)
            
            status = "✅ 通过" if analysis.get('passed') else "❌ 拒绝"
            print(f"    {status} | 类型: {analysis.get('type')} | 分数: {analysis.get('relevance_score')} | 置信度: {analysis.get('confidence')}")
            print(f"    原因: {analysis.get('reason')}")
            
            if analysis.get('passed'):
                passed_items.append({
                    'name': repo['name'],
                    'url': repo.get('repo_url', ''),
                    'type': analysis.get('type'),
                    'category': analysis.get('category'),
                    'score': analysis.get('relevance_score'),
                    'confidence': analysis.get('confidence'),
                    'reason': analysis.get('reason'),
                    'agent_evidence': analysis.get('agent_evidence'),
                    'embodied_evidence': analysis.get('embodied_evidence')
                })
            else:
                rejected_items.append({
                    'name': repo['name'],
                    'url': repo.get('repo_url', ''),
                    'reason': analysis.get('reason'),
                    'confidence': analysis.get('confidence')
                })
        else:
            print(f"    ⚠️ API调用失败")
        print()
    
    # 输出汇总
    print("\n" + "=" * 80)
    print(f"审核结果: {len(passed_items)} 通过 / {len(rejected_items)} 拒绝")
    print("=" * 80)
    
    if passed_items:
        print("\n✅ 通过项目（可上传）:")
        print("-" * 80)
        for item in passed_items:
            print(f"\n• {item['name']}")
            print(f"  URL: {item['url']}")
            print(f"  类型: {item['type']} | 分类: {item['category']} | 分数: {item['score']}/10")
            print(f"  原因: {item['reason']}")
    
    # 保存结果到JSON（供用户确认）
    result_file = f"/home/ubuntu/.openclaw/workspace/upload_candidates_{int(datetime.now().timestamp())}.json"
    with open(result_file, 'w') as f:
        json.dump({
            'passed': passed_items,
            'rejected_count': len(rejected_items),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n\n💾 可上传清单已保存: {result_file}")
    print(f"📊 通过率: {len(passed_items)}/{len(batch)} ({len(passed_items)/len(batch)*100:.1f}%)")
    
    return passed_items

if __name__ == '__main__':
    main()
