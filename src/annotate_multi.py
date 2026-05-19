#!/usr/bin/env python3
"""
ROSClaw LLM Annotator - Multi-Threaded High Performance Version
使用线程池并发调用阿里云API，大幅提升标注速度
"""

API_KEY = "BAILIAN_KEY_PLACEHOLDER"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.5-plus"
DB_PATH = "rosclaw_hub.db"
MAX_WORKERS = 5   # 降低并发避免限流
BATCH_SIZE = 15   # 降低批次大小
API_TIMEOUT = 25  # API超时
RETRY_COUNT = 3   # 重试次数

import json
import sqlite3
import requests
import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 线程锁保护日志写入
log_lock = threading.Lock()

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    with log_lock:
        print(line, flush=True)
        with open('annotate_multi.log', 'a') as f:
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

def call_qwen(repo):
    """调用阿里云API进行标注 - 带重试机制"""
    prompt = f"""Analyze this repo for ROSClaw Physical AI relevance:
Name: {repo['name']}
Type: {repo['type']}
URL: {repo['repo_url']}
Stars: {repo['stars']}
Desc: {repo['description'] or 'N/A'}

Score 0-100 (higher if robotics/embodied AI/ROS/simulation/control/hardware).
Return ONLY JSON with: summary, relevance_score, category, subcategory, robot_types, tags, capabilities, hardware_requirements, software_dependencies, is_rosclaw_native, confidence"""
    
    headers = {"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 1500
    }
    
    for attempt in range(RETRY_COUNT):
        try:
            r = requests.post(BASE_URL + "/chat/completions", headers=headers, json=payload, timeout=API_TIMEOUT)
            if r.status_code == 200:
                content = r.json()['choices'][0]['message']['content']
                content = content.strip()
                if content.startswith('```json'): content = content[7:]
                if content.startswith('```'): content = content[3:]
                if content.endswith('```'): content = content[:-3]
                return json.loads(content.strip())
            elif r.status_code == 429:
                time.sleep(2 ** attempt)  # 指数退避
                continue
            elif r.status_code >= 500:
                time.sleep(1)
                continue
            else:
                return None
        except requests.exceptions.Timeout:
            if attempt < RETRY_COUNT - 1:
                time.sleep(1)
                continue
        except Exception as e:
            if attempt < RETRY_COUNT - 1:
                time.sleep(1)
                continue
    
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
            log(f"  DB update error for ID {repo_id}: {str(e)[:50]}")
    
    conn.commit()
    conn.close()
    return updated

def process_batch(batch_num):
    """处理一批仓库 - 使用线程池并发调用API"""
    repos = get_batch(BATCH_SIZE)
    if not repos:
        return 0, 0
    
    log(f"Batch #{batch_num} | Processing {len(repos)} repos with {MAX_WORKERS} threads...")
    
    # 使用线程池并发调用API
    results = []
    success_count = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有任务
        future_to_repo = {
            executor.submit(call_qwen, repo): repo 
            for repo in repos
        }
        
        # 收集结果
        for future in as_completed(future_to_repo):
            repo = future_to_repo[future]
            try:
                result = future.result(timeout=35)
                if result:
                    results.append((repo['id'], result))
                    success_count += 1
                    score = result.get('relevance_score', 0)
                    log(f"  ✅ {repo['name'][:25]:<25} Score: {score:>3}/100")
                else:
                    log(f"  ❌ {repo['name'][:25]:<25} API failed")
            except Exception as e:
                log(f"  ❌ {repo['name'][:25]:<25} Error: {str(e)[:30]}")
    
    # 批量写入数据库
    updated = update_db_batch(results)
    log(f"Batch #{batch_num} complete: {updated}/{len(repos)} updated")
    
    # 批次间休息，避免API限流
    time.sleep(3)
    
    return updated, len(repos)

def main():
    log("=" * 70)
    log("🚀 ROSClaw LLM Annotator - Multi-Threaded v3")
    log(f"⚡ Config: {MAX_WORKERS} threads | {BATCH_SIZE} per batch")
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
        
        log(f"📊 Progress: {total_processed}/{total_attempted} | Rate: {rate:.1f}/min | Remaining: ~{unannotated}")
        
        if unannotated <= 0:
            break
        
        # 批次间短暂休息
        time.sleep(2)
    
    elapsed_total = time.time() - start_time
    log("=" * 70)
    log("🎉 Annotation complete!")
    log(f"Total: {total_processed} repos in {elapsed_total/60:.1f} minutes")
    log(f"Avg rate: {total_processed/(elapsed_total/60):.1f} repos/min")
    log("=" * 70)

if __name__ == '__main__':
    main()
