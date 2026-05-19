#!/usr/bin/env python3
"""
ROSClaw LLM Annotator - Singapore Node Multi-Threaded
使用新加坡API Key，5并发高速标注
"""

API_KEY = "os.getenv("DEEPSEEK_API_KEY", "")"
BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.5-plus"
DB_PATH = "rosclaw_hub.db"
MAX_WORKERS = 3    # 降低并发减少失败
BATCH_SIZE = 9     # 每批9条
API_TIMEOUT = 90   # 增加超时

import json, sqlite3, requests, time, threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

log_lock = threading.Lock()

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    with log_lock:
        print(line, flush=True)
        with open('annotate_sg.log', 'a') as f:
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
    prompt = f"""Rate this repo 0-100 for robotics/embodied AI/ROS relevance.
Name: {repo['name']}
Type: {repo['type']}
Stars: {repo['stars']}
Desc: {repo['description'] or 'N/A'}

Return JSON: summary, relevance_score, category, subcategory, robot_types, tags, capabilities, hardware_requirements, software_dependencies, is_rosclaw_native, confidence"""
    
    headers = {"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 1500
    }
    
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
            log(f"  ⚠️ Rate limited")
            time.sleep(5)
            return None
        else:
            return None
    except Exception as e:
        return None

def update_db_batch(results):
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

def process_batch(batch_num):
    repos = get_batch(BATCH_SIZE)
    if not repos:
        return 0, 0
    
    log(f"Batch #{batch_num} | {len(repos)} repos | {MAX_WORKERS} workers...")
    
    results = []
    success = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_repo = {executor.submit(call_qwen, repo): repo for repo in repos}
        
        for future in as_completed(future_to_repo):
            repo = future_to_repo[future]
            try:
                result = future.result(timeout=API_TIMEOUT+10)
                if result:
                    results.append((repo['id'], result))
                    success += 1
                    score = result.get('relevance_score', 0)
                    log(f"  ✅ {repo['name'][:25]:<25} Score: {score:>3}/100")
                else:
                    log(f"  ❌ {repo['name'][:25]:<25} Failed")
            except Exception as e:
                log(f"  ❌ {repo['name'][:25]:<25} Error")
    
    updated = update_db_batch(results)
    log(f"Batch #{batch_num} done: {updated}/{len(repos)}")
    time.sleep(5)  # 批次间休息5秒
    return updated, len(repos)

def main():
    log("=" * 60)
    log("🚀 ROSClaw Singapore Annotator v5")
    log("⚡ 5 workers | 15 per batch | Singapore node")
    log("=" * 60)
    
    total = 0
    attempted = 0
    batch_num = 0
    start = time.time()
    
    while True:
        unannotated, qwen_done = get_stats()
        if unannotated == 0:
            log("✅ All done!")
            break
        
        batch_num += 1
        success, count = process_batch(batch_num)
        total += success
        attempted += count
        
        elapsed = time.time() - start
        rate = total / (elapsed / 60) if elapsed > 0 else 0
        
        log(f"📊 Progress: {total}/{attempted} | Rate: {rate:.1f}/min | Remaining: ~{unannotated}")
    
    elapsed = time.time() - start
    log("=" * 60)
    log(f"🎉 Complete! {total} repos in {elapsed/60:.1f} min")
    log(f"Rate: {total/(elapsed/60):.1f}/min")
    log("=" * 60)

if __name__ == '__main__':
    main()
