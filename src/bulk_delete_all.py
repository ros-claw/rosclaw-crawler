#!/usr/bin/env python3
"""
删除ROSClaw网站上所有项目（通过API查询并删除）
"""

import sqlite3
import json
import time
import requests
from datetime import datetime

DB_PATH = '/home/ubuntu/.openclaw/workspace/rosclaw_crawler/rosclaw_hub.db'
API_KEY = '"${ROSCALW_API_KEY}"'
BASE_URL = 'https://www.rosclaw.io'
MCP_ENDPOINT = f'{BASE_URL}/api/mcp-packages'
SKILL_ENDPOINT = f'{BASE_URL}/api/skills'

HEADERS = {
    'Content-Type': 'application/json',
    'X-API-Key': API_KEY
}

def get_all_site_items(endpoint, item_type):
    """分页获取网站上所有项目"""
    all_items = []
    page = 1
    limit = 100
    
    while True:
        try:
            resp = requests.get(
                f"{endpoint}?page={page}&limit={limit}",
                headers=HEADERS,
                timeout=30
            )
            if resp.status_code != 200:
                print(f"  ⚠️ 获取{item_type}列表失败: HTTP {resp.status_code}")
                break
            
            data = resp.json()
            items = data if isinstance(data, list) else data.get('items', data.get('data', []))
            
            if not items:
                break
            
            all_items.extend(items)
            print(f"  第{page}页获取 {len(items)} 个{item_type}")
            
            if len(items) < limit:
                break
            
            page += 1
            time.sleep(0.5)
            
        except Exception as e:
            print(f"  ⚠️ 获取{item_type}列表出错: {e}")
            break
    
    return all_items

def delete_item_by_id(item_id, endpoint_base, item_name):
    """通过ID删除项目"""
    try:
        delete_endpoint = f"{endpoint_base}?id={item_id}"
        response = requests.delete(
            delete_endpoint,
            headers=HEADERS,
            timeout=30
        )
        
        if response.status_code in [200, 201, 204]:
            return True, f"Deleted ({response.status_code})"
        elif response.status_code == 404:
            return True, f"Not found (404)"
        
        return False, f"HTTP {response.status_code}: {response.text[:200]}"
    
    except requests.exceptions.RequestException as e:
        return False, f"Request error: {str(e)}"
    except Exception as e:
        return False, f"Error: {str(e)}"

def reset_db_status_by_url(repo_url):
    """根据repo_url重置数据库状态"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE rosclaw_hub_resources 
            SET llm_upload_status='pending_review',
                llm_uploaded_at=NULL,
                llm_upload_error=NULL
            WHERE repo_url=?
        """, (repo_url,))
        
        conn.commit()
        updated = cursor.rowcount
        conn.close()
        return updated
    except Exception as e:
        print(f"    ⚠️ 数据库更新失败: {e}")
        return 0

def main():
    start_time = time.time()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    print("=" * 60)
    print("ROSClaw 网站项目全量删除工具")
    print("=" * 60)
    
    # 获取网站上所有MCP包
    print("\n📦 获取MCP包列表...")
    mcp_items = get_all_site_items(MCP_ENDPOINT, 'MCP')
    print(f"网站上共有 {len(mcp_items)} 个MCP包")
    
    # 获取网站上所有Skills
    print("\n🔧 获取Skill列表...")
    skill_items = get_all_site_items(SKILL_ENDPOINT, 'Skill')
    print(f"网站上共有 {len(skill_items)} 个Skill")
    
    total = len(mcp_items) + len(skill_items)
    print(f"\n网站上项目总数: {total}")
    
    if total == 0:
        print("网站上没有项目，退出")
        return
    
    # 删除MCP包
    success_count = 0
    fail_count = 0
    results = []
    
    print("\n" + "=" * 60)
    print("开始删除MCP包...")
    print("=" * 60)
    
    for i, item in enumerate(mcp_items, 1):
        item_id = item.get('id')
        name = item.get('name', 'unknown')
        repo_url = item.get('githubRepoUrl', '')
        
        print(f"\n[{i}/{len(mcp_items)}] 删除MCP: {name}")
        
        success, msg = delete_item_by_id(item_id, MCP_ENDPOINT, name)
        
        # 重置数据库状态
        if repo_url:
            reset_db_status_by_url(repo_url)
        
        if success:
            success_count += 1
            print(f"  ✅ {msg}")
        else:
            fail_count += 1
            print(f"  ❌ {msg}")
        
        results.append({
            'type': 'mcp',
            'name': name,
            'id': item_id,
            'success': success,
            'message': msg
        })
        
        time.sleep(0.3)
    
    # 删除Skills
    print("\n" + "=" * 60)
    print("开始删除Skills...")
    print("=" * 60)
    
    for i, item in enumerate(skill_items, 1):
        item_id = item.get('id')
        name = item.get('name', 'unknown')
        repo_url = item.get('githubRepoUrl', '')
        
        print(f"\n[{i}/{len(skill_items)}] 删除Skill: {name}")
        
        success, msg = delete_item_by_id(item_id, SKILL_ENDPOINT, name)
        
        # 重置数据库状态
        if repo_url:
            reset_db_status_by_url(repo_url)
        
        if success:
            success_count += 1
            print(f"  ✅ {msg}")
        else:
            fail_count += 1
            print(f"  ❌ {msg}")
        
        results.append({
            'type': 'skill',
            'name': name,
            'id': item_id,
            'success': success,
            'message': msg
        })
        
        time.sleep(0.3)
    
    # 计算耗时
    elapsed = time.time() - start_time
    
    # 生成日志文件
    log_data = {
        'timestamp': timestamp,
        'total': total,
        'success': success_count,
        'failed': fail_count,
        'elapsed_seconds': round(elapsed, 2),
        'results': results
    }
    
    log_filename = f'/home/ubuntu/.openclaw/workspace/rosclaw_crawler/bulk_delete_complete_{timestamp}.json'
    with open(log_filename, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    
    # 输出统计
    print("\n" + "=" * 60)
    print("删除完成!")
    print("=" * 60)
    print(f"总计: {total}")
    print(f"成功删除: {success_count}")
    print(f"失败: {fail_count}")
    print(f"耗时: {elapsed:.2f}秒")
    print(f"日志文件: {log_filename}")
    
    # 验证删除结果
    print("\n🔍 验证删除结果...")
    remaining_mcp = get_all_site_items(MCP_ENDPOINT, 'MCP')
    remaining_skill = get_all_site_items(SKILL_ENDPOINT, 'Skill')
    print(f"网站上剩余MCP: {len(remaining_mcp)}")
    print(f"网站上剩余Skill: {len(remaining_skill)}")
    
    return log_data

if __name__ == '__main__':
    main()
