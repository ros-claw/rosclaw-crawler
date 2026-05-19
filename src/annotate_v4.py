#!/usr/bin/env python3
"""
ROSClaw LLM Annotator - Optimized Concurrent Version v4
使用requests.Session和适配器，控制并发避免限流
"""

API_KEY = "os.getenv("DEEPSEEK_API_KEY", "")"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # 北京节点（API Key仅在此有效）
MODEL = "qwen3.5-plus"
DB_PATH = "rosclaw_hub.db"
MAX_WORKERS = 2    # 北京节点限流严格，只开2并发
BATCH_SIZE = 6     # 每批6条
API_TIMEOUT = 60   # 北京节点实际5秒，留余量

import json
import sqlite3
import requests
import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
import os

# 创建带连接池的session
def create_session():
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=3)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session

# 线程锁保护日志
log_lock = threading.Lock()

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    with log_lock:
        print(line, flush=True)
        with open('annotate_v4.log', 'a') as f:
            f.write(line + '\n')

def get_stats():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM rosclaw_hub_resources WHERE is_relevant = 1 AND llm_analyzed_at IS NULL")
    unannotated = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM rosclaw_hub_resources WHERE is_relevant = 1 AND llm_model = 'qwen3.5-plus'")
    qwen_done = c.fetchone()[0]
    conn.close()
    return unannotated, qwen_done

def get_batch(limit=BATCH_SIZE):
    conn = sqlite3.connect(DB_PATH, timeout=30)
    c = conn.cursor()
    c.execute("""
        SELECT id, type, repo_url, name, description, stars
        FROM rosclaw_hub_resources
        WHERE is_relevant = 1 AND llm_analyzed_at IS NULL
        ORDER BY stars DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [{'id': r[0], 'type': r[1], 'repo_url': r[2], 'name': r[3], 'description': r[4], 'stars': r[5]} for r in rows]

def call_qwen(repo, session):
    """调用阿里云API进行标注"""
    prompt = f"""Rate this repo 0-100 for robotics/embodied AI/ROS relevance.

Name: {repo['name']}
Type: {repo['type']}
Stars: {repo['stars']}
Desc: {repo['description'] or 'N/A'}

Return JSON: summary, relevance_score(0-100), category, subcategory, robot_types, tags, capabilities, hardware_requirements, software_dependencies, is_rosclaw_native, confidence"""
    
    headers = {"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 1500
    }
    
    try:
        r = session.post(BASE_URL + "/chat/completions", headers=headers, json=payload, timeout=API_TIMEOUT)
        if r.status_code == 200:
            content = r.json()['choices'][0]['message']['content']
            content = content.strip()
            if content.startswith('```json'): content = content[7:]
            if content.startswith('```'): content = content[3:]
            if content.endswith('```'): content = content[:-3]
            return json.loads(content.strip())
        elif r.status_code == 429:
            time.sleep(5)
            return None
        else:
            return None
    except Exception as e:
        return None

def update_db_batch(results):
    """批量更新数据库"""
    conn = sqlite3.connect(DB_PATH, timeout=60)
    c = conn.cursor()
    
    updated = 0
    for repo_id, result in results:
        if result is None:
            continue
            
        features = {
            'subcategory': result.get('subcategory', ''),
            'robot_types': result.get('robot_types', []),
            'tags': result.get('tags', []),
            'capabilities': result.get('capabilities', []),
            'hardware_requirements': result.get('hardware_requirements', []),
            'software_dependencies': result.get('software_dependencies', []),
            'confidence': result.get('confidence', 0)
        }
        score = result.get('relevance_score', 0)
        
        try:
            c.execute("""
                UPDATE rosclaw_hub_resources SET
                    llm_summary = ?, llm_relevance_score = ?, llm_category = ?,
                    llm_key_features = ?, llm_analyzed_at = ?, llm_model = ?,
                    domain_tags = ?, is_embodied = ?
                WHERE id = ?
            """, (
                result.get('summary', ''), score, result.get('category', 'Unknown'),
                json.dumps(features, ensure_ascii=False), datetime.now().isoformat(), MODEL,
                json.dumps(result.get('tags', []), ensure_ascii=False),
                result.get('is_rosclaw_native', False) or score >= 70,
                repo_id
            ))
            updated += 1
        except Exception as e:
            pass
    
    conn.commit()
    conn.close()
    return updated

def process_repo(repo, session):
    """处理单个仓库"""
    result = call_qwen(repo, session)
    return repo['id'], repo['name'], result

def process_batch(batch_num):
    """处理一批仓库"""
    repos = get_batch(BATCH_SIZE)
    if not repos:
        return 0, 0
    
    log(f"Batch #{batch_num} | Processing {len(repos)} repos with {MAX_WORKERS} workers...")
    
    # 创建共享session
    session = create_session()
    
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_repo = {
            executor.submit(process_repo, repo, session): repo 
            for repo in repos
        }
        
        for future in as_completed(future_to_repo):
            repo_id, name, result = future.result()
            results.append((repo_id, result))
            if result:
                score = result.get('relevance_score', 0)
                log(f"  ✅ {name[:28]:<28} Score: {score:>3}/100")
            else:
                log(f"  ❌ {name[:28]:<28} Failed")
    
    session.close()
    
    # 批量写入
    updated = update_db_batch(results)
    log(f"Batch #{batch_num} complete: {updated}/{len(repos)} updated")
    
    # 批次间休息
    time.sleep(3)
    
    return updated, len(repos)

def main():
    log("=" * 70)
    log("🚀 ROSClaw LLM Annotator v4 - Optimized Concurrent")
    log(f"⚡ Config: {MAX_WORKERS} workers | {BATCH_SIZE} per batch")
    log("=" * 70)
    
    total_processed = 0
    total_attempted = 0
    batch_num = 0
    start_time = time.time()
    
    while True:
        unannotated, qwen_done = get_stats()
        
        if unannotated == 0:
            log("✅ All repositories annotated!")
            break
        
        batch_num += 1
        success, attempted = process_batch(batch_num)
        
        total_processed += success
        total_attempted += attempted
        
        elapsed = time.time() - start_time
        rate = total_processed / (elapsed / 60) if elapsed > 0 else 0
        
        log(f"📊 Total: {total_processed}/{total_attempted} | Rate: {rate:.1f}/min | Remaining: ~{unannotated}")
        
        if unannotated <= 0:
            break
    
    elapsed_total = time.time() - start_time
    log("=" * 70)
    log("🎉 Complete!")
    log(f"Total: {total_processed} repos in {elapsed_total/60:.1f} minutes")
    log(f"Rate: {total_processed/(elapsed_total/60):.1f} repos/min")
    log("=" * 70)

if __name__ == '__main__':
    main()
