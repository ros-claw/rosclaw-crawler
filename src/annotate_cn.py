#!/usr/bin/env python3
"""ROSClaw Annotator - Beijing Node (id%3==0)"""
API_KEY = "BAILIAN_KEY_PLACEHOLDER"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.5-plus"
DB_PATH = "rosclaw_hub.db"
MY_MOD = 0
API_TIMEOUT = 120

import json, sqlite3, requests, time
from datetime import datetime

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] [CN] {msg}", flush=True)
    with open('annotate_3way.log', 'a') as f:
        f.write(f"[{ts}] [CN] {msg}\n")

def get_one_repo():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    c = conn.cursor()
    c.execute("""
        SELECT id, type, repo_url, name, description, stars
        FROM rosclaw_hub_resources
        WHERE is_relevant=1 AND llm_analyzed_at IS NULL AND id % 3 = ?
        ORDER BY RANDOM() LIMIT 1
    """, (MY_MOD,))
    row = c.fetchone()
    conn.close()
    if not row: return None
    return {'id': row[0], 'type': row[1], 'repo_url': row[2], 'name': row[3], 'description': row[4], 'stars': row[5]}

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
            log("  ⚠️ Rate limited")
            time.sleep(60)
    except Exception as e:
        log(f"  ⚠️ Error: {str(e)[:40]}")
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

def main():
    log("=" * 50)
    log("🇨🇳 Beijing Node Started (id%3==0)")
    log("=" * 50)
    total = 0
    fails = 0
    start = time.time()
    
    while True:
        repo = get_one_repo()
        if not repo:
            log("✅ No more repos for me!")
            break
        
        log(f"→ {repo['name']} (⭐{repo['stars']})")
        result = call_api(repo)
        
        if result:
            try:
                update_db(repo['id'], result)
                total += 1
                fails = 0
                log(f"  ✅ Score: {result.get('relevance_score',0)}/100 | {result.get('category','?')[:20]}")
            except Exception as e:
                log(f"  ❌ DB: {str(e)[:30]}")
        else:
            fails += 1
            log(f"  ❌ Failed ({fails} consecutive)")
            if fails >= 5:
                log("  ⏹️ Too many failures, pausing 60s...")
                time.sleep(60)
                fails = 0
        
        time.sleep(5)
    
    elapsed = time.time() - start
    log(f"🎉 Done! {total} repos in {elapsed/60:.1f}min")

if __name__ == '__main__':
    main()
