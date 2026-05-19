#!/usr/bin/env python3
"""
稳定批量删除rosclaw.io非MCP项目
带断点续传、慢速请求、进度保存
"""

import requests
import json
import re
import time
import os
from datetime import datetime

API_KEY = '"${ROSCALW_API_KEY}"'
BASE_URL = 'https://www.rosclaw.io'
MCP_ENDPOINT = f'{BASE_URL}/api/mcp-packages'
HEADERS = {'Content-Type': 'application/json', 'X-API-Key': API_KEY}

PROGRESS_FILE = 'delete_progress.json'

# === FAKE判定规则 ===
FAKE_PATTERNS = [
    # 游戏引擎（无物理硬件）
    r'unreal[\s\-_]?mcp', r'unity[\s\-_]?mcp', r'blender[\s\-_]?mcp',
    r'ue[\s\-_]?cortex', r'uefn[\s\-_]?mcp', r'ue[\s\-_]?blueprint',
    # 纯软件/办公工具
    r'second[\s\-_]?brain', r'3d[\s\-_]?software', r'cad[\s\-_]?mcp',
    r'databricks', r'smart[\s\-_]?coding', r'rossum',
    r'n8n',
    # 非硬件IoT
    r'iotdb', r'tapo',
    # 其他明显非MCP
    r'funplay', r'openbrain', r'voltron',
    r'roslyn', r'meupc', r'mcpd',
    r'apple[\s\-_]?silicon',
]

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {'deleted_ids': [], 'failed_ids': []}

def save_progress(progress):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

def get_all_items():
    """获取所有MCP包"""
    resp = requests.get(f'{MCP_ENDPOINT}?page=1&limit=1000', headers=HEADERS, timeout=30)
    data = resp.json()
    items = data if isinstance(data, list) else data.get('items', data.get('data', []))
    return items

def is_fake(item):
    name = item.get('name', '').lower()
    url = item.get('githubRepoUrl', '').lower()
    text = f'{name} {url}'
    
    # 硬性排除
    for pattern in FAKE_PATTERNS:
        if re.search(pattern, text):
            return True, f'Pattern: {pattern}'
    
    # 名字不含mcp → 不是MCP项目
    if 'mcp' not in name:
        return True, 'No mcp in name'
    
    return False, ''

def delete_item(item_id):
    try:
        resp = requests.delete(f'{MCP_ENDPOINT}?id={item_id}', headers=HEADERS, timeout=30)
        return resp.status_code in [200, 201, 204], resp.status_code
    except Exception as e:
        return False, str(e)

def main():
    print("=" * 60)
    print("ROSClaw 非MCP项目清理")
    print("=" * 60)
    
    # 加载进度
    progress = load_progress()
    already_deleted = set(progress['deleted_ids'])
    already_failed = set(progress['failed_ids'])
    
    # 获取所有项目
    print("\n📦 获取项目列表...")
    items = get_all_items()
    print(f"网站上共有 {len(items)} 个MCP包")
    
    # 筛选FAKE
    fake_items = []
    for item in items:
        is_f, reason = is_fake(item)
        if is_f:
            item['_reason'] = reason
            fake_items.append(item)
    
    print(f"标记为FAKE: {len(fake_items)} 个")
    
    # 排除已处理的
    to_delete = []
    for item in fake_items:
        if item['id'] not in already_deleted and item['id'] not in already_failed:
            to_delete.append(item)
    
    print(f"待删除（排除已处理）: {len(to_delete)} 个")
    
    if not to_delete:
        print("\n✅ 所有FAKE项目已处理完毕！")
        return
    
    # 执行删除
    success = 0
    failed = 0
    
    for i, item in enumerate(to_delete, 1):
        item_id = item['id']
        name = item['name']
        reason = item['_reason']
        
        print(f"\n[{i}/{len(to_delete)}] {name}")
        print(f"  原因: {reason}")
        
        ok, code = delete_item(item_id)
        
        if ok:
            success += 1
            progress['deleted_ids'].append(item_id)
            print(f"  ✅ 删除成功 ({code})")
        else:
            failed += 1
            progress['failed_ids'].append(item_id)
            print(f"  ❌ 删除失败 ({code})")
        
        # 保存进度
        save_progress(progress)
        
        # 慢速控制：每5个暂停2秒
        if i % 5 == 0:
            print(f"  ⏳ 已处理 {i}/{len(to_delete)}，暂停2秒...")
            time.sleep(2)
        else:
            time.sleep(0.5)
    
    # 最终统计
    print("\n" + "=" * 60)
    print("本轮完成!")
    print(f"尝试删除: {len(to_delete)}")
    print(f"成功: {success}")
    print(f"失败: {failed}")
    print(f"累计已删: {len(progress['deleted_ids'])}")
    print(f"累计失败: {len(progress['failed_ids'])}")
    
    # 验证剩余
    print("\n🔍 验证剩余...")
    remaining = get_all_items()
    print(f"网站上剩余MCP: {len(remaining)}")

if __name__ == '__main__':
    main()
