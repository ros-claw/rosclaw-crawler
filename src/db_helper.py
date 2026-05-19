import sqlite3
from datetime import datetime

DB_PATH = '/home/ubuntu/.openclaw/workspace/rosclaw_crawler/rosclaw_hub.db'

def get_unanalyzed_repos(limit=5):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, description, stars, domain_tags, repo_url, type
        FROM rosclaw_hub_resources 
        WHERE is_relevant=1 AND llm_analyzed_at IS NULL 
        ORDER BY id LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_repo_analysis(repo_id, summary, score, category, features, model='kimi-k2p5-agent'):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    features_str = '|'.join(features) if isinstance(features, list) else features
    cursor.execute('''
        UPDATE rosclaw_hub_resources 
        SET llm_summary = ?, llm_relevance_score = ?, llm_category = ?, 
            llm_key_features = ?, llm_analyzed_at = ?, llm_model = ?
        WHERE id = ?
    ''', (summary, score, category, features_str, datetime.utcnow().isoformat(), model, repo_id))
    conn.commit()
    conn.close()

def count_unanalyzed():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM rosclaw_hub_resources WHERE is_relevant=1 AND llm_analyzed_at IS NULL')
    count = cursor.fetchone()[0]
    conn.close()
    return count

if __name__ == '__main__':
    count = count_unanalyzed()
    print(f"Total unanalyzed repos: {count}")
    repos = get_unanalyzed_repos()
    print(f"Fetched {len(repos)} repos to analyze")
    for r in repos:
        print(f"  [{r['id']}] {r['name']} - {r['type']}")
        print(f"      Desc: {r['description'][:100] if r['description'] else 'N/A'}...")
        print(f"      Stars: {r['stars']}, Tags: {r['domain_tags']}")
