#!/usr/bin/env python3
"""
删除ROSClaw网站上所有已上传的项目
"""

import sqlite3
import json
import time
import requests
from datetime import datetime
from urllib.parse import urlparse

DB_PATH = '/home/ubuntu/.openclaw/workspace/rosclaw_crawler/rosclaw_hub.db'
API_KEY = '"${ROSCALW_API_KEY}"'
BASE_URL = 'https://www.rosclaw.io'
MCP_ENDPOINT = f'{BASE_URL}/api/mcp-packages'
SKILL_ENDPOINT = f'{BASE_URL}/api/skills'

HEADERS = {
    'Content-Type': 'application/json',
    'X-API-Key': API_KEY
}

def get_owner_repo(repo_url):
    """从GitHub URL提取owner和repo"""
    path = urlparse(repo_url).path.strip('/')
    parts = path.split('/')
    if len(parts) >= 2:
        return parts[0], parts[1]
    return parts[0] if parts else 'unknown', 'unknown'

def get_uploaded_items():
    """获取所有已上传项目"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, repo_url, llm_upload_type, llm_upload_category
        FROM rosclaw_hub_resources 
        WHERE llm_upload_status='uploaded'
    """)
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items

def delete_item(item):
    """删除单个项目"""
    owner, repo = get_owner_repo(item['repo_url'])
    name = f"{owner}/{repo}"
    upload_type = item.get('llm_upload_type')
    
    # 首先通过GET获取项目ID
    if upload_type == 'mcp':
        list_endpoint = f"{MCP_ENDPOINT}?search={name}&limit=1"
        delete_endpoint_base = MCP_ENDPOINT
    elif upload_type == 'skill':
        list_endpoint = f"{SKILL_ENDPOINT}?search={name}&limit=1"
        delete_endpoint_base = SKILL_ENDPOINT
    else:
        return False, f"Unknown upload type: {upload_type}"
    
    try:
        # 先获取项目ID
        resp = requests.get(list_endpoint, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            return False, f"List failed: HTTP {resp.status_code}"
        
        data = resp.json()
        items_list = data if isinstance(data, list) else data.get('items', data.get('data', []))
        
        if not items_list:
            return True, "Not found - already deleted"
        
        pkg_id = items_list[0].get('id')
        if not pkg_id:
            return False, "No id field in response"
        
        # 通过id参数删除
        delete_endpoint = f"{delete_endpoint_base}?id={pkg_id}"
        response = requests.delete(
            delete_endpoint,
            headers=HEADERS,
            timeout=30
        )
        
        if response.status_code in [200, 201, 204]:
            return True, f"Deleted ({response.status_code})"
        elif response.status_code == 404:
            return True, f"Not found (404) - already deleted"
        
        return False, f"HTTP {response.status_code}: {response.text[:200]}"
    
    except requests.exceptions.RequestException as e:
        return False, f"Request error: {str(e)}"
    except Exception as e:
        return False, f"Error: {str(e)}"

def update_status_reset(item_id):
    """重置数据库状态为待审核"""
    max_retries = 5
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE rosclaw_hub_resources 
                SET llm_upload_status='pending_review',
                    llm_uploaded_at=NULL,
                    llm_upload_error=NULL
                WHERE id=?
            """, (item_id,))
            
            conn.commit()
            conn.close()
            return True
        except sqlite3.OperationalError as e:
            if 'locked' in str(e).lower() and attempt < max_retries - 1:
                print(f"    ⚠️ 数据库锁定，重试 {attempt+1}/{max_retries}...")
                time.sleep(2 ** attempt)
                continue
            else:
                print(f"    ❌ 数据库更新失败: {e}")
                return False
    return False

def main():
    start_time = time.time()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    print("=" * 60)
    print("ROSClaw 批量删除工具")
    print("=" * 60)
    
    # 获取已上传项目
    items = get_uploaded_items()
    total = len(items)
    print(f"\n已上传项目总数: {total}")
    
    if total == 0:
        print("没有已上传项目，退出")
        return
    
    # 统计
    success_count = 0
    fail_count = 0
    not_found_count = 0
    results = []
    
    for i, item in enumerate(items, 1):
        item_id = item['id']
        name = item.get('name', 'unknown')
        upload_type = item.get('llm_upload_type', 'unknown')
        
        print(f"\n[{i}/{total}] 删除 {upload_type}: {name} (ID: {item_id})")
        
        # 删除
        success, msg = delete_item(item)
        
        # 无论API删除是否成功，都重置数据库状态
        # 如果404说明已经不存在了，也算清理完成
        if success:
            update_status_reset(item_id)
            if 'Not found' in msg:
                not_found_count += 1
                print(f"  ✅ 已不存在: {msg}")
            else:
                success_count += 1
                print(f"  ✅ 成功删除: {msg}")
        else:
            fail_count += 1
            print(f"  ❌ 删除失败: {msg}")
            # 即使删除失败，也重置状态以便重新处理
            update_status_reset(item_id)
        
        # 记录结果
        result = {
            'id': item_id,
            'name': name,
            'type': upload_type,
            'success': success,
            'message': msg,
            'timestamp': datetime.now().isoformat()
        }
        results.append(result)
        
        # 速率控制
        if i % 5 == 0:
            print(f"\n  ⏳ 已处理 {i}/{total}，暂停1秒...")
            time.sleep(1)
    
    # 计算耗时
    elapsed = time.time() - start_time
    
    # 生成日志文件
    log_data = {
        'timestamp': timestamp,
        'total': total,
        'success': success_count,
        'not_found': not_found_count,
        'failed': fail_count,
        'elapsed_seconds': round(elapsed, 2),
        'results': results
    }
    
    log_filename = f'/home/ubuntu/.openclaw/workspace/rosclaw_crawler/bulk_delete_result_{timestamp}.json'
    with open(log_filename, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    
    # 输出统计
    print("\n" + "=" * 60)
    print("删除完成!")
    print("=" * 60)
    print(f"总计: {total}")
    print(f"成功删除: {success_count}")
    print(f"已不存在: {not_found_count}")
    print(f"失败: {fail_count}")
    print(f"耗时: {elapsed:.2f}秒")
    print(f"日志文件: {log_filename}")
    
    return log_data

if __name__ == '__main__':
    main()
