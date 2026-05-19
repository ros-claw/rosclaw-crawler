#!/usr/bin/env python3
"""
ROSClaw LLM Annotator - Optimized Version
高效处理，减少等待时间，增加并发
"""

API_KEY = "BAILIAN_KEY_PLACEHOLDER"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.5-plus"
DB_PATH = "rosclaw_hub.db"

import json, sqlite3, requests, time
from datetime import datetime

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open('annotate_fast.log', 'a') as f:
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

def get_batch(limit=15):
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
    prompt = f"""Analyze this repo for ROSClaw Physical AI relevance:
Name: {repo['name']}
Type: {repo['type']}
URL: {repo['repo_url']}
Stars: {repo['stars']}
Desc: {repo['description'] or 'N/A'}

Score 0-100 (higher if robotics/embodied AI/ROS/simulation/control/hardware).
Return ONLY JSON with: summary, relevance_score, category, subcategory, robot_types, tags, capabilities, hardware_requirements, software_dependencies, is_rosclaw_native, confidence"""
    
    headers = {"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"}
    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 1500}
    
    try:
        r = requests.post(BASE_URL + "/chat/completions", headers=headers, json=payload, timeout=120)
        if r.status_code == 200:
            content = r.json()['choices'][0]['message']['content']
            content = content.strip()
            if content.startswith('```json'): content = content[7:]
            if content.startswith('```'): content = content[3:]
            if content.endswith('```'): content = content[:-3]
            return json.loads(content.strip())
        elif r.status_code == 429:
            log(f"  ⚠️ API限流，等待30秒...")
            time.sleep(30)
            return None
        else:
            log(f"  ⚠️ API错误 {r.status_code}: {r.text[:80]}")
    except requests.exceptions.Timeout:
        log(f"  ⚠️ API超时")
    except Exception as e:
        log(f"  ⚠️ API异常: {str(e)[:80]}")
    return None

def update_db(repo_id, result):
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
    
    conn = sqlite3.connect(DB_PATH, timeout=60)
    c = conn.cursor()
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
    conn.commit()
    conn.close()

def main():
    log("=" * 60)
    log("🤖 ROSClaw Fast Annotator Started")
    log("=" * 60)
    
    total_processed = 0
    batch_num = 0
    start_time = time.time()
    
    while True:
        unannotated, qwen_done = get_stats()
        
        if unannotated == 0:
            log("✅ All repositories annotated!")
            break
        
        batch_num += 1
        log(f"Batch #{batch_num} | Remaining: {unannotated} | Qwen done: {qwen_done}")
        
        # Get batch
        repos = get_batch(15)
        if not repos:
            break
        
        # Process batch
        success = 0
        for i, repo in enumerate(repos):
            log(f"  [{i+1}/{len(repos)}] {repo['name']} (⭐{repo['stars']})")
            
            result = call_qwen(repo)
            if result:
                try:
                    update_db(repo['id'], result)
                    score = result.get('relevance_score', 0)
                    success += 1
                    total_processed += 1
                    log(f"    ✅ Score: {score}/100 | {result.get('category', '?')[:20]}")
                except Exception as e:
                    log(f"    ❌ DB error: {str(e)[:50]}")
            else:
                log(f"    ❌ API failed")
            
            time.sleep(0.5)
        
        elapsed = time.time() - start_time
        rate = total_processed / (elapsed / 60) if elapsed > 0 else 0
        log(f"Batch done: {success}/{len(repos)} success | Total: {total_processed} | Rate: {rate:.1f}/min")
        
        if unannotated <= 0:
            break
        
        time.sleep(5)
    
    log("=" * 60)
    log("🎉 Annotation complete!")
    log(f"Total processed: {total_processed}")
    log("=" * 60)

if __name__ == '__main__':
    main()
