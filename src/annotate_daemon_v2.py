#!/usr/bin/env python3
"""
ROSClaw LLM Annotator Daemon v2
后台持续标注，自动处理crawler冲突，带数据库重试
"""

API_KEY = ""${DEEPSEEK_API_KEY}""
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.5-plus"
DB_PATH = "rosclaw_hub.db"
CRAWLER_PID = 503963

import json, sqlite3, requests, time, os, signal
from datetime import datetime

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def get_stats():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM rosclaw_hub_resources WHERE is_relevant = 1 AND llm_analyzed_at IS NULL")
    unannotated = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM rosclaw_hub_resources WHERE is_relevant = 1 AND llm_model = 'qwen3.5-plus'")
    qwen_done = c.fetchone()[0]
    conn.close()
    return unannotated, qwen_done

def get_batch(limit=10):
    conn = sqlite3.connect(DB_PATH, timeout=10)
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
        r = requests.post(BASE_URL + "/chat/completions", headers=headers, json=payload, timeout=180)
        if r.status_code == 200:
            content = r.json()['choices'][0]['message']['content']
            content = content.strip()
            if content.startswith('```json'): content = content[7:]
            if content.startswith('```'): content = content[3:]
            if content.endswith('```'): content = content[:-3]
            return json.loads(content.strip())
        else:
            log(f"API Error {r.status_code}: {r.text[:100]}")
    except Exception as e:
        log(f"API Exception: {str(e)[:100]}")
    return None

def update_db(repo_id, result, max_retries=10):
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
    
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30)
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
            return True
        except sqlite3.OperationalError as e:
            if 'database is locked' in str(e) and attempt < max_retries - 1:
                wait = min(2 ** attempt, 60)
                log(f"DB locked, retrying in {wait}s... (attempt {attempt+1})")
                time.sleep(wait)
            else:
                log(f"DB update failed after {max_retries} retries: {str(e)[:50]}")
                return False
        except Exception as e:
            log(f"DB update error: {str(e)[:50]}")
            return False
    return False

def stop_crawler():
    try:
        os.kill(CRAWLER_PID, signal.SIGSTOP)
        log(f"Paused crawler (PID {CRAWLER_PID})")
        time.sleep(3)  # Wait for any pending DB operations to finish
    except:
        pass

def start_crawler():
    try:
        os.kill(CRAWLER_PID, signal.SIGCONT)
        log(f"Resumed crawler (PID {CRAWLER_PID})")
    except:
        pass

def main():
    log("=" * 60)
    log("🤖 ROSClaw LLM Annotator Daemon v2 Started")
    log("=" * 60)
    
    total_processed = 0
    batch_num = 0
    
    while True:
        try:
            unannotated, qwen_done = get_stats()
            
            if unannotated == 0:
                log("✅ All repositories annotated!")
                start_crawler()
                break
            
            batch_num += 1
            log(f"Batch #{batch_num} | Remaining: {unannotated} | Qwen done: {qwen_done}")
            
            # Pause crawler for DB access
            stop_crawler()
            
            # Get batch
            repos = get_batch(5)  # Smaller batch to avoid long lock times
            if not repos:
                start_crawler()
                break
            
            # Process batch
            success = 0
            for i, repo in enumerate(repos):
                result = call_qwen(repo)
                if result:
                    if update_db(repo['id'], result):
                        success += 1
                        total_processed += 1
                else:
                    log(f"Failed: {repo['name']}")
                
                time.sleep(1)
            
            log(f"Batch complete: {success}/{len(repos)} success | Total: {total_processed}")
            
            # Resume crawler
            start_crawler()
            
            # Rest between batches
            time.sleep(15)
            
        except Exception as e:
            log(f"Main loop error: {str(e)[:100]}")
            start_crawler()
            time.sleep(30)

if __name__ == '__main__':
    main()
