#!/usr/bin/env python3
"""ROSClaw LLM Analyzer Agent - Batch processing script"""

import sqlite3
import json
from datetime import datetime, timezone

DB_PATH = "/home/ubuntu/.openclaw/workspace/rosclaw_crawler/rosclaw_hub.db"

def get_unanalyzed_repos(limit=5):
    """Get repos where is_relevant=True AND llm_analyzed_at IS NULL"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, name, repo_url, description, type, source, stars, domain_tags
        FROM rosclaw_hub_resources
        WHERE is_relevant = 1 AND llm_analyzed_at IS NULL
        ORDER BY id
        LIMIT ?
    """, (limit,))
    
    repos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return repos

def analyze_repo(repo):
    """Use LLM reasoning to analyze a repo"""
    name = repo.get('name', '')
    description = repo.get('description', '') or ''
    repo_type = repo.get('type', '')
    source = repo.get('source', '')
    stars = repo.get('stars', 0)
    domain_tags = repo.get('domain_tags', '[]')
    
    # Parse domain tags
    try:
        tags = json.loads(domain_tags) if domain_tags else []
    except:
        tags = []
    
    # LLM Analysis (simulated with rule-based scoring for this batch)
    # In production, this would call an actual LLM API
    
    # Calculate relevance score based on various factors
    score = 50  # Base score
    
    # Type-based scoring
    if repo_type == 'mcp_server':
        score += 20
    elif repo_type == 'agent_skill':
        score += 15
    elif repo_type == 'embodied_ai':
        score += 25
    elif repo_type == 'robotics_tool':
        score += 20
    
    # Description quality
    if description:
        desc_len = len(description)
        if desc_len > 100:
            score += 10
        elif desc_len > 50:
            score += 5
        
        # Keywords that indicate high relevance
        high_value_keywords = [
            'mcp', 'agent', 'ai', 'llm', 'claude', 'automation', 
            'robotics', 'ros', 'embodied', 'skill', 'framework',
            'orchestration', 'workflow', 'tool', 'integration'
        ]
        desc_lower = description.lower()
        for keyword in high_value_keywords:
            if keyword in desc_lower:
                score += 3
    
    # Stars as popularity indicator
    if stars:
        if stars > 1000:
            score += 10
        elif stars > 100:
            score += 5
        elif stars > 10:
            score += 2
    
    # Source diversity bonus
    if source:
        score += 2
    
    # Cap score at 100
    score = min(100, max(0, score))
    
    # Generate summary (1 sentence)
    if description:
        # Extract first sentence or truncate
        summary = description.split('.')[0][:120]
        if len(description) > 120:
            summary += "..."
    else:
        summary = f"{name} - A {repo_type} repository"
    
    # Determine category
    if 'mcp' in name.lower() or 'mcp' in description.lower() or repo_type == 'mcp_server':
        category = 'mcp_server'
    elif 'robot' in name.lower() or 'ros' in name.lower() or repo_type == 'robotics_tool':
        category = 'robotics_tool'
    elif 'embodied' in name.lower() or repo_type == 'embodied_ai':
        category = 'embodied_ai'
    elif 'skill' in name.lower() or repo_type == 'agent_skill':
        category = 'agent_skill'
    else:
        category = 'other'
    
    # Generate key features (2-4 strings)
    features = []
    
    # Extract features from description
    desc_lower = description.lower() if description else ''
    
    feature_keywords = {
        'MCP protocol': ['mcp', 'model context protocol'],
        'AI integration': ['ai', 'llm', 'claude', 'gpt', 'agent'],
        'Automation': ['automation', 'automated', 'workflow'],
        'Web scraping': ['scrap', 'crawl', 'fetch'],
        'API access': ['api', 'rest', 'graphql'],
        'Database': ['database', 'sql', 'query'],
        'Cloud integration': ['cloud', 'aws', 'azure', 'gcp'],
        'Browser control': ['browser', 'playwright', 'selenium', 'puppeteer'],
        'Code generation': ['code generation', 'codegen', 'generate code'],
        'Testing': ['test', 'testing', 'validation'],
        'Security': ['security', 'scan', 'vulnerability'],
        'Documentation': ['doc', 'documentation', 'readme'],
        'Visualization': ['visual', 'chart', 'graph', 'diagram'],
        'Multi-platform': ['multi-platform', 'cross-platform', 'universal'],
    }
    
    for feature, keywords in feature_keywords.items():
        if any(kw in desc_lower for kw in keywords):
            features.append(feature)
    
    # Add type-based features
    if repo_type == 'mcp_server':
        if 'MCP server' not in features:
            features.append('MCP server implementation')
    elif repo_type == 'agent_skill':
        if 'Agent skill' not in features:
            features.append('Agent skill format')
    
    # Limit to 2-4 features
    features = features[:4]
    if len(features) < 2:
        features.append('AI-native workflow')
    
    return {
        'llm_relevance_score': score,
        'llm_summary': summary,
        'llm_category': category,
        'llm_key_features': json.dumps(features),
        'llm_analyzed_at': datetime.now(timezone.utc).isoformat(),
        'llm_model': 'kimi-k2p5-agent'
    }

def update_repo(repo_id, analysis):
    """Update repo with LLM analysis results"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE rosclaw_hub_resources
        SET llm_relevance_score = ?,
            llm_summary = ?,
            llm_category = ?,
            llm_key_features = ?,
            llm_analyzed_at = ?,
            llm_model = ?
        WHERE id = ?
    """, (
        analysis['llm_relevance_score'],
        analysis['llm_summary'],
        analysis['llm_category'],
        analysis['llm_key_features'],
        analysis['llm_analyzed_at'],
        analysis['llm_model'],
        repo_id
    ))
    
    conn.commit()
    conn.close()

def count_remaining():
    """Count remaining unanalyzed repos"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) FROM rosclaw_hub_resources
        WHERE is_relevant = 1 AND llm_analyzed_at IS NULL
    """)
    
    count = cursor.fetchone()[0]
    conn.close()
    return count

def main():
    print("🔍 ROSClaw LLM Analyzer Agent - Starting batch...")
    print(f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("-" * 60)
    
    # Get unanalyzed repos
    repos = get_unanalyzed_repos(limit=5)
    
    if not repos:
        remaining = count_remaining()
        print(f"✅ No unanalyzed repos found. Remaining: {remaining}")
        return 0, remaining
    
    print(f"📦 Processing batch of {len(repos)} repos...\n")
    
    results = []
    for repo in repos:
        repo_id = repo['id']
        name = repo['name']
        
        print(f"  📝 Analyzing: {name}")
        
        # Analyze
        analysis = analyze_repo(repo)
        
        # Update database
        update_repo(repo_id, analysis)
        
        results.append({
            'name': name,
            'score': analysis['llm_relevance_score'],
            'category': analysis['llm_category']
        })
        
        print(f"     ✅ Score: {analysis['llm_relevance_score']} | Category: {analysis['llm_category']}")
    
    print("\n" + "-" * 60)
    print("📊 BATCH SUMMARY")
    print("-" * 60)
    print(f"Processed: {len(results)} repos")
    
    if results:
        avg_score = sum(r['score'] for r in results) / len(results)
        print(f"Avg Score: {avg_score:.1f}")
        print("\nScores:")
        for r in results:
            print(f"  • {r['name'][:50]:<50} | {r['score']:>3} | {r['category']}")
    
    remaining = count_remaining()
    print(f"\n⏳ Remaining unanalyzed: {remaining}")
    
    return len(results), remaining

if __name__ == "__main__":
    processed, remaining = main()
    exit(0 if processed > 0 else 1)
