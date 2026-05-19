#!/usr/bin/env python3
"""
ROSClaw 上传清单生成器
基于已审核的数据库，生成可上传项目清单
"""
import sqlite3
import json
from datetime import datetime, timezone

DB_PATH = '/home/ubuntu/.openclaw/workspace/rosclaw_crawler/rosclaw_hub.db'

def generate_upload_list(min_score=7, confidence='medium'):
    """生成可上传清单"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 查询通过审核的项目
    cursor.execute('''
        SELECT id, name, description, repo_url, stars, 
               llm_relevance_score, llm_category, llm_summary, llm_key_features
        FROM rosclaw_hub_resources
        WHERE llm_model = 'deepseek-v4-pro'
          AND llm_relevance_score >= ?
        ORDER BY llm_relevance_score DESC, stars DESC
    ''', (min_score,))
    
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    # 解析key_features JSON
    upload_list = []
    for row in rows:
        features = {}
        if row.get('llm_key_features'):
            try:
                features = json.loads(row['llm_key_features'])
            except:
                pass
        
        upload_list.append({
            'id': row['id'],
            'name': row['name'],
            'url': row['repo_url'],
            'stars': row['stars'],
            'type': features.get('type', 'unknown'),
            'category': row.get('llm_category', 'general'),
            'score': row.get('llm_relevance_score', 0),
            'confidence': features.get('confidence', 'unknown'),
            'reason': row.get('llm_summary', ''),
            'agent_evidence': features.get('agent_evidence', ''),
            'embodied_evidence': features.get('embodied_evidence', '')
        })
    
    return upload_list

def main():
    print("=" * 80)
    print("ROSClaw 可上传清单生成器")
    print("=" * 80)
    
    # 生成清单
    upload_list = generate_upload_list(min_score=7)
    
    print(f"\n找到 {len(upload_list)} 个通过严格审核的项目\n")
    
    if not upload_list:
        print("没有通过审核的项目！请先运行 strict_analyze.py")
        return
    
    # 按类型分组
    mcp_items = [item for item in upload_list if item['type'] == 'mcp']
    skill_items = [item for item in upload_list if item['type'] == 'skill']
    
    print(f"MCP Server: {len(mcp_items)} 个")
    print(f"Agent Skill: {len(skill_items)} 个")
    print()
    
    # 输出详情
    print("=" * 80)
    print("可上传项目详情:")
    print("=" * 80)
    
    for item in upload_list:
        print(f"\n• {item['name']} (⭐{item['stars']})")
        print(f"  URL: {item['url']}")
        print(f"  类型: {item['type']} | 分类: {item['category']} | 分数: {item['score']}/10")
        print(f"  原因: {item['reason']}")
        print(f"  Agent证据: {item['agent_evidence']}")
        print(f"  具身证据: {item['embodied_evidence']}")
    
    # 保存清单
    result_file = f"/home/ubuntu/.openclaw/workspace/upload_list_{int(datetime.now().timestamp())}.json"
    with open(result_file, 'w') as f:
        json.dump({
            'total': len(upload_list),
            'mcp_count': len(mcp_items),
            'skill_count': len(skill_items),
            'items': upload_list,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n\n💾 清单已保存: {result_file}")
    print(f"\n⚠️ 注意: 这是本地输出，尚未上传！")
    print(f"请确认清单后，运行上传脚本进行实际上传。")

if __name__ == '__main__':
    main()
