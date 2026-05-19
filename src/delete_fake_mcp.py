#!/usr/bin/env python3
"""
删除rosclaw.io上明显非MCP的项目（第一轮清理）
"""

import requests
import json
import re
import time
from datetime import datetime

API_KEY = '"${ROSCALW_API_KEY}"'
BASE_URL = 'https://www.rosclaw.io'
MCP_ENDPOINT = f'{BASE_URL}/api/mcp-packages'
HEADERS = {'Content-Type': 'application/json', 'X-API-Key': API_KEY}

# 明显非MCP的模式（游戏引擎、纯软件工具、非硬件相关）
FAKE_PATTERNS = [
    r'unreal[\s\-_]?mcp', r'unity[\s\-_]?mcp', r'blender[\s\-_]?mcp',
    r'second[\s\-_]?brain', r'3d[\s\-_]?software', r'cad[\s\-_]?mcp',
    r'iotdb', r'tapo', r'rossum',
    r'funplay', r'openbrain', r'voltron',
    r'uecortex', r'roslyn', r'databricks',
    r'smart[\s\-_]?coding', r'meupc', r'mcpd',
    r'n8n', r'apple[\s\-_]?silicon',
    r'uefn', r'ue[\s\-_]?blueprint',
]

def get_all_items():
    resp = requests.get(f'{MCP_ENDPOINT}?page=1&limit=1000', headers=HEADERS, timeout=30)
    data = resp.json()
    return data if isinstance(data, list) else data.get('items', data.get('data', []))

def is_fake(item):
    name = item.get('name', '').lower()
    url = item.get('githubRepoUrl', '').lower()
    text = f'{name} {url}'
    if any(re.search(p, text) for p in FAKE_PATTERNS):
        return True
    if 'mcp' not in name:
        return True
    return False

def delete_item(item_id):
    try:
        resp = requests.delete(f'{MCP_ENDPOINT}?id={item_id}', headers=HEADERS, timeout=30)
        return resp.status_code in [200, 201, 204], resp.status_code
    except Exception as e:
        return False, str(e)

def main():
    print("=" * 60)
    print("ROSClaw 第一轮清理 - 删除明显非MCP项目")
    print("=" * 60)
    
    items = get_all_items()
    print(f"\n网站上共有 {len(items)} 个MCP包")
    
    fake_items = [i for i in items if is_fake(i)]
    print(f"标记为FAKE: {len(fake_items)} 个")
    
    if not fake_items:
        print("没有需要删除的项目")
        return
    
    # 执行删除
    success = 0
    failed = 0
    results = []
    
    for i, item in enumerate(fake_items, 1):
        item_id = item.get('id')
        name = item.get('name', 'unknown')
        print(f"\n[{i}/{len(fake_items)}] 删除 {name}")
        
        ok, code = delete_item(item_id)
        if ok:
            success += 1
            print(f"  ✅ 成功 ({code})")
        else:
            failed += 1
            print(f"  ❌ 失败 ({code})")
        
        results.append({'name': name, 'id': item_id, 'success': ok, 'code': str(code)})
        time.sleep(0.2)
    
    # 保存日志
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log = {
        'timestamp': timestamp,
        'total_fake': len(fake_items),
        'success': success,
        'failed': failed,
        'results': results
    }
    with open(f'mcp_delete_round1_{timestamp}.json', 'w') as f:
        json.dump(log, f, indent=2)
    
    print("\n" + "=" * 60)
    print("第一轮清理完成!")
    print(f"总计: {len(fake_items)}")
    print(f"成功: {success}")
    print(f"失败: {failed}")
    
    # 验证
    remaining = get_all_items()
    print(f"\n剩余MCP: {len(remaining)}")

if __name__ == '__main__':
    main()
