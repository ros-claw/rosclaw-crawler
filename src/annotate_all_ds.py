#!/usr/bin/env python3
"""ROSClaw Annotator - DeepSeek Multi-Worker (all remaining repos)"""
API_KEY = "os.getenv("DEEPSEEK_API_KEY", "")"
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-v4-flash"
DB_PATH = "rosclaw_hub.db"
API_TIMEOUT = 90
NUM_WORKERS = 5  # 并发数

import json, sqlite3, requests, time, threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

lock = threading.Lock()
total_done = 0


def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] [DS-MULTI] {msg}", flush=True)
    with lock:
        with open('annotate_multi_final.log', 'a') as f:
            f.write(f"[{ts}] [DS-MULTI] {msg}\n")


def get_repos_batch(limit=50):
    """获取一批未标注的repo（不限mod）"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    c = conn.cursor()
    c.execute("""
        SELECT id, type, repo_url, name, description, stars
        FROM rosclaw_hub_resources
        WHERE is_relevant=1 AND llm_analyzed_at IS NULL
        ORDER BY RANDOM() LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [{'id': r[0], 'type': r[1], 'repo_url': r[2], 'name': r[3], 'description': r[4], 'stars': r[5]} for r in rows]


def call_api(repo):
    prompt = f"""Rate repo 0-100 for robotics/embodied AI/ROS relevance.
Name: {repo['name']}\nType: {repo['type']}\nStars: {repo['stars']}\nDesc: {repo['description'] or 'N/A'}
Return JSON: summary, relevance_score, category, subcategory, robot_types, tags, capabilities, hardware_requirements, software_dependencies, is_rosclaw_native, confidence"""
    headers = {"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"}
    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 1500}
    try:
        r = requests.post(BASE_URL + "/chat/completions", headers=headers, json=payload, timeout=API_TIMEOUT)
        if r.status_code == 200:
            content = r.json()['choices'][0]['message']['content'].strip()
            if content.startswith('```json'): content = content[7:]
            if content.startswith('```'): content = content[3:]
            if content.endswith('```'): content = content[:-3]
            return json.loads(content.strip())
        elif r.status_code == 429:
            log(f"  ⚠️ Rate limited on {repo['name']}")
            time.sleep(30)
    except Exception as e:
        log(f"  ⚠️ Error on {repo['name']}: {str(e)[:40]}")
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
    for attempt in range(10):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            c = conn.cursor()
            c.execute("""UPDATE rosclaw_hub_resources SET
                llm_summary=?, llm_relevance_score=?, llm_category=?,
                llm_key_features=?, llm_analyzed_at=?, llm_model=?,
                domain_tags=?, is_embodied=? WHERE id=?""", (
                result.get('summary',''), score, result.get('category','Unknown'),
                json.dumps(features, ensure_ascii=False), datetime.now().isoformat(), MODEL,
                json.dumps(result.get('tags',[]), ensure_ascii=False),
                result.get('is_rosclaw_native', False) or score >= 70, repo_id))
            conn.commit()
            conn.close()
            return True
        except sqlite3.OperationalError as e:
            if 'database is locked' in str(e) and attempt < 9:
                time.sleep(2 ** attempt)
            else:
                raise
    return False


def process_repo(repo):
    global total_done
    result = call_api(repo)
    if result:
        try:
            update_db(repo['id'], result)
            with lock:
                total_done += 1
                current_total = total_done
            log(f"  ✅ {repo['name']}: {result.get('relevance_score',0)}/100 | Total: {current_total}")
            return True
        except Exception as e:
            log(f"  ❌ DB error on {repo['name']}: {str(e)[:30]}")
    else:
        log(f"  ❌ Failed: {repo['name']}")
    return False


def main():
    log("=" * 60)
    log(f"🔥 DeepSeek Multi-Worker Started ({NUM_WORKERS} workers)")
    log("=" * 60)
    start = time.time()
    batch_num = 0

    while True:
        repos = get_repos_batch(100)
        if not repos:
            log("✅ No more repos!")
            break

        batch_num += 1
        log(f"Batch #{batch_num} | {len(repos)} repos | {NUM_WORKERS} workers")

        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            futures = {executor.submit(process_repo, repo): repo for repo in repos}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    log(f"  💥 Worker exception: {str(e)[:40]}")

        # 检查是否还有剩余
        conn = sqlite3.connect(DB_PATH, timeout=30)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM rosclaw_hub_resources WHERE is_relevant=1 AND llm_analyzed_at IS NULL")
        remaining = c.fetchone()[0]
        conn.close()
        log(f"📊 Remaining: {remaining} | Done this batch: {total_done}")

        if remaining == 0:
            break

    elapsed = time.time() - start
    log(f"🎉 ALL DONE! {total_done} repos in {elapsed/60:.1f}min")


if __name__ == '__main__':
    main()
