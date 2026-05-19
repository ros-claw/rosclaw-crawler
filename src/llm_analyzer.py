#!/usr/bin/env python3
"""ROSClaw LLM Analyzer Agent - Batch Analysis Script"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from database import init_db, get_session, RosclawHubResource
from sqlalchemy import and_
import requests
import json

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rosclaw_hub.db")
LLM_API_BASE = "https://api.kimi.com/coding/"
LLM_API_KEY = "sk-kimi-vrz2fy5ydvh8ffJ9gdppuELATikXXvWT5tslriqiYFRo0YxCWzwrQLutPfugt3Um"
LLM_MODEL = "kimi"

def analyze_repo_with_llm(repo: RosclawHubResource) -> dict:
    """Use LLM to analyze a repository and return analysis results."""
    
    prompt = f"""Analyze this GitHub repository for relevance to robotics, embodied AI, MCP servers, or agent skills.

Repository: {repo.name or 'N/A'}
URL: {repo.repo_url}
Description: {repo.description or 'N/A'}
Type: {repo.type}
Stars: {repo.stars}
Domain Tags: {repo.domain_tags or []}

Provide your analysis in this exact JSON format:
{{
  "relevance_score": <0-100, how relevant is this to robotics/embodied AI/agent ecosystem>,
  "summary": "<one sentence summary of what this repo does>",
  "category": "<one of: mcp_server, agent_skill, embodied_ai, robotics_tool, other>",
  "key_features": ["<feature1>", "<feature2>", "<feature3>"]
}}

Category definitions:
- mcp_server: Model Context Protocol server implementation
- agent_skill: Agent skill/plugin for AI assistants
- embodied_ai: Physical AI, robotics, manipulation, navigation
- robotics_tool: Tool/framework for robotics development
- other: None of the above but still relevant

Respond ONLY with valid JSON."""

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 500
    }
    
    try:
        proxies = {"https": "socks5h://127.0.0.1:1080", "http": "socks5h://127.0.0.1:1080"}
        response = requests.post(
            f"{LLM_API_BASE}chat/completions",
            headers=headers,
            json=data,
            proxies=proxies,
            timeout=60
        )
        response.raise_for_status()
        
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        
        # Extract JSON from markdown code block if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        analysis = json.loads(content)
        return {
            "llm_relevance_score": analysis.get("relevance_score", 50),
            "llm_summary": analysis.get("summary", "No summary generated"),
            "llm_category": analysis.get("category", "other"),
            "llm_key_features": json.dumps(analysis.get("key_features", [])),
            "success": True
        }
    except Exception as e:
        print(f"  ⚠️ LLM analysis failed for {repo.name}: {e}")
        return {
            "llm_relevance_score": 0,
            "llm_summary": f"Analysis failed: {str(e)[:100]}",
            "llm_category": "other",
            "llm_key_features": "[]",
            "success": False
        }

def process_batch(batch_size: int = 5) -> dict:
    """Process a batch of repos for LLM analysis."""
    engine = init_db(DB_PATH)
    session = get_session(engine)
    
    try:
        # Query repos needing analysis
        repos = session.query(RosclawHubResource).filter(
            and_(
                RosclawHubResource.is_relevant == True,
                RosclawHubResource.llm_analyzed_at.is_(None)
            )
        ).order_by(RosclawHubResource.id).limit(batch_size).all()
        
        if not repos:
            return {"processed": 0, "results": [], "remaining": 0}
        
        results = []
        print(f"🤖 ROSClaw LLM Analyzer - Processing batch of {len(repos)} repos\n")
        
        for repo in repos:
            print(f"📦 Analyzing: {repo.name or repo.repo_url}")
            
            analysis = analyze_repo_with_llm(repo)
            
            # Update repo with analysis
            repo.llm_relevance_score = analysis["llm_relevance_score"]
            repo.llm_summary = analysis["llm_summary"]
            repo.llm_category = analysis["llm_category"]
            repo.llm_key_features = analysis["llm_key_features"]
            repo.llm_analyzed_at = datetime.utcnow()
            repo.llm_model = "kimi-k2p5-agent"
            
            session.commit()
            
            results.append({
                "id": repo.id,
                "name": repo.name,
                "score": analysis["llm_relevance_score"],
                "category": analysis["llm_category"],
                "success": analysis["success"]
            })
            
            status = "✅" if analysis["success"] else "⚠️"
            print(f"  {status} Score: {analysis['llm_relevance_score']} | Category: {analysis['llm_category']}")
            print(f"  📝 {analysis['llm_summary'][:80]}...")
            print()
        
        # Check remaining
        remaining = session.query(RosclawHubResource).filter(
            and_(
                RosclawHubResource.is_relevant == True,
                RosclawHubResource.llm_analyzed_at.is_(None)
            )
        ).count()
        
        return {
            "processed": len(repos),
            "results": results,
            "remaining": remaining
        }
        
    finally:
        session.close()

def run_llm_analysis_chunk(session, batch_size: int = 3) -> tuple:
    """Analyze a batch of repos using the provided session. Returns (processed, success)."""
    # TEMP: Skip LLM analysis until new API key is provided
    if not LLM_API_KEY or LLM_API_KEY == "sk-kimi-vrz2fy5ydvh8ffJ9gdppuELATikXXvWT5tslriqiYFRo0YxCWzwrQLutPfugt3Um":
        return 0, 0

    from sqlalchemy import and_

    repos = session.query(RosclawHubResource).filter(
        and_(
            RosclawHubResource.is_relevant == True,
            RosclawHubResource.llm_analyzed_at.is_(None)
        )
    ).order_by(RosclawHubResource.id).limit(batch_size).all()

    if not repos:
        return 0, 0

    success_count = 0
    for repo in repos:
        analysis = analyze_repo_with_llm(repo)
        repo.llm_relevance_score = analysis["llm_relevance_score"]
        repo.llm_summary = analysis["llm_summary"]
        repo.llm_category = analysis["llm_category"]
        repo.llm_key_features = analysis["llm_key_features"]
        repo.llm_analyzed_at = datetime.utcnow()
        repo.llm_model = "kimi-k2p5-agent"
        session.merge(repo)
        if analysis["success"]:
            success_count += 1

    session.commit()
    return len(repos), success_count


if __name__ == "__main__":
    result = process_batch(5)
    
    if result["processed"] == 0:
        print("🎉 No more repos to analyze! All caught up.")
    else:
        print(f"\n📊 Batch Complete: {result['processed']} repos analyzed")
        print(f"📈 Scores: {[r['score'] for r in result['results']]}")
        print(f"🔄 Remaining: {result['remaining']} repos")
        
        if result['remaining'] > 0:
            print("\n⏭️ More repos waiting... trigger next batch!")
            sys.exit(42)  # Signal to continue processing
        else:
            print("\n✅ All repos analyzed!")
            sys.exit(0)
