#!/usr/bin/env python3
"""
上传高质量项目到ROSClaw网站（严格审核后）
只上传 llm_upload_status='pending_api' 的项目
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
    path = urlparse(repo_url).path.strip('/')
    parts = path.split('/')
    if len(parts) >= 2:
        return parts[0], parts[1]
    return parts[0] if parts else 'unknown', 'unknown'

def get_pending_items():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, repo_url, llm_upload_type, llm_summary, description,
               llm_category, stars, llm_upload_tags, llm_upload_tools, 
               llm_upload_dependencies, llm_relevance_score
        FROM rosclaw_hub_resources 
        WHERE llm_upload_status='pending_api'
        ORDER BY llm_relevance_score DESC, stars DESC
    """)
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items

def build_mcp_payload(item):
    owner, repo = get_owner_repo(item['repo_url'])
    name = f"{owner}/{repo}"
    
    tags = []
    if item.get('llm_upload_tags'):
        try:
            if isinstance(item['llm_upload_tags'], str):
                tags = json.loads(item['llm_upload_tags'])
            else:
                tags = item['llm_upload_tags']
        except:
            tags = [t.strip() for t in item['llm_upload_tags'].split(',') if t.strip()]
    
    tools = []
    if item.get('llm_upload_tools'):
        try:
            if isinstance(item['llm_upload_tools'], str):
                tools = json.loads(item['llm_upload_tools'])
            else:
                tools = item['llm_upload_tools']
        except:
            tools = []
    
    payload = {
        "name": name,
        "description": item.get('llm_summary') or item.get('description') or '',
        "long_description": item.get('description') or '',
        "readme_content": "",
        "github_repo_url": item['repo_url'],
        "author_name": owner,
        "category": item.get('llm_category') or 'General',
        "robot_type": "universal",
        "tags": tags if tags else [],
        "version": "1.0.0",
        "tools": tools if tools else [],
        "github_stars": item.get('stars') or 0
    }
    return payload

def build_skill_payload(item):
    owner, repo = get_owner_repo(item['repo_url'])
    name = f"{owner}/{repo}"
    
    tags = []
    if item.get('llm_upload_tags'):
        try:
            if isinstance(item['llm_upload_tags'], str):
                tags = json.loads(item['llm_upload_tags'])
            else:
                tags = item['llm_upload_tags']
        except:
            tags = [t.strip() for t in item['llm_upload_tags'].split(',') if t.strip()]
    
    dependencies = []
    if item.get('llm_upload_dependencies'):
        try:
            if isinstance(item['llm_upload_dependencies'], str):
                dependencies = json.loads(item['llm_upload_dependencies'])
            else:
                dependencies = item['llm_upload_dependencies']
        except:
            dependencies = []
    
    payload = {
        "name": name,
        "display_name": item.get('name') or repo,
        "description": item.get('llm_summary') or item.get('description') or '',
        "long_description": item.get('description') or '',
        "readme_content": "",
        "github_repo_url": item['repo_url'],
        "author_name": owner,
        "category": item.get('llm_category') or 'General',
        "robot_types": ["universal"],
        "compatible_robots": [],
        "tags": tags if tags else [],
        "version": "1.0.0",
        "dependencies": dependencies if dependencies else [],
        "github_stars": item.get('stars') or 0
    }
    return payload

def upload_item(item):
    upload_type = item.get('llm_upload_type')
    
    if upload_type == 'mcp':
        payload = build_mcp_payload(item)
        endpoint = MCP_ENDPOINT
    elif upload_type == 'skill':
        payload = build_skill_payload(item)
        endpoint = SKILL_ENDPOINT
    else:
        return False, f"Unknown upload type: {upload_type}"
    
    try:
        response = requests.post(
            endpoint,
            headers=HEADERS,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 409:
            return True, f"Already exists (409)"
        
        if response.status_code in [200, 201]:
            return True, f"Success ({response.status_code})"
        
        return False, f"HTTP {response.status_code}: {response.text[:200]}"
    
    except requests.exceptions.RequestException as e:
        return False, f"Request error: {str(e)}"
    except Exception as e:
        return False, f"Error: {str(e)}"

def update_status(item_id, success, error_msg):
    max_retries = 5
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            cursor = conn.cursor()
            
            if success:
                cursor.execute("""
                    UPDATE rosclaw_hub_resources 
                    SET llm_upload_status='uploaded', 
                        llm_uploaded_at=?,
                        llm_upload_error=NULL
                    WHERE id=?
                """, (datetime.now().isoformat(), item_id))
            else:
                cursor.execute("""
                    UPDATE rosclaw_hub_resources 
                    SET llm_upload_status='failed', 
                        llm_upload_error=?,
                        llm_uploaded_at=?
                    WHERE id=?
                """, (error_msg, datetime.now().isoformat(), item_id))
            
            conn.commit()
            conn.close()
            return True
        except sqlite3.OperationalError as e:
            if 'locked' in str(e).lower() and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            else:
                return False
    return False

def main():
    start_time = time.time()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    print("=" * 60)
    print("ROSClaw 批量上传工具（严格审核后）")
    print("=" * 60)
    
    items = get_pending_items()
    total = len(items)
    print(f"\n待上传项目总数: {total}")
    
    if total == 0:
        print("没有待上传项目，退出")
        return
    
    success_count = 0
    fail_count = 0
    already_exists_count = 0
    results = []
    
    for i, item in enumerate(items, 1):
        item_id = item['id']
        name = item.get('name', 'unknown')
        upload_type = item.get('llm_upload_type', 'unknown')
        score = item.get('llm_relevance_score', 0)
        
        print(f"\n[{i}/{total}] 上传 {upload_type}: {name} (score={score})")
        
        success, msg = upload_item(item)
        update_status(item_id, success, msg)
        
        result = {
            'id': item_id,
            'name': name,
            'type': upload_type,
            'success': success,
            'message': msg,
            'timestamp': datetime.now().isoformat()
        }
        results.append(result)
        
        if success:
            if 'Already exists' in msg:
                already_exists_count += 1
                print(f"  ✅ 已存在: {msg}")
            else:
                success_count += 1
                print(f"  ✅ 成功: {msg}")
        else:
            fail_count += 1
            print(f"  ❌ 失败: {msg}")
        
        if i % 10 == 0:
            print(f"\n  ⏳ 已处理 {i}/{total}，暂停1秒...")
            time.sleep(1)
    
    elapsed = time.time() - start_time
    
    log_data = {
        'timestamp': timestamp,
        'total': total,
        'success': success_count,
        'already_exists': already_exists_count,
        'failed': fail_count,
        'elapsed_seconds': round(elapsed, 2),
        'results': results
    }
    
    log_filename = f'/home/ubuntu/.openclaw/workspace/rosclaw_crawler/bulk_upload_strict_{timestamp}.json'
    with open(log_filename, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 60)
    print("上传完成!")
    print("=" * 60)
    print(f"总计: {total}")
    print(f"成功上传: {success_count}")
    print(f"已存在: {already_exists_count}")
    print(f"失败: {fail_count}")
    print(f"耗时: {elapsed:.2f}秒")
    print(f"日志文件: {log_filename}")
    
    return log_data

if __name__ == '__main__':
    main()
