#!/usr/bin/env python3
"""Batch LLM analysis for ROSClaw Hub resources."""
import sqlite3
import json
from datetime import datetime

# Analysis results for the batch
analyses = [
    {
        "id": 6607,
        "name": "sd-webui-lobe-theme",
        "llm_relevance_score": 65,
        "llm_summary": "A modern theme for Stable Diffusion WebUI that provides an enhanced user interface for AI image generation workflows.",
        "llm_category": "other",
        "llm_key_features": ["Modern UI theme", "SD WebUI integration", "Enhanced UX for image gen", "Customizable interface"]
    },
    {
        "id": 6608,
        "name": "lobe-cli-toolbox",
        "llm_relevance_score": 78,
        "llm_summary": "Collection of CLI tools for LobeHub ecosystem providing command-line utilities for agent development and deployment.",
        "llm_category": "agent_skill",
        "llm_key_features": ["CLI utilities", "Agent development tools", "LobeHub integration", "Command-line automation"]
    },
    {
        "id": 6609,
        "name": "lobe-ui",
        "llm_relevance_score": 75,
        "llm_summary": "React UI component library designed for building conversational AI and agent interfaces with modern design patterns.",
        "llm_category": "agent_skill",
        "llm_key_features": ["React components", "Chat UI patterns", "Agent interface design", "LobeChat integration"]
    },
    {
        "id": 6610,
        "name": "lobe-icons",
        "llm_relevance_score": 55,
        "llm_summary": "Icon library providing consistent visual assets for LobeHub applications and agent interfaces.",
        "llm_category": "other",
        "llm_key_features": ["SVG icons", "Brand consistency", "AI-themed icons", "Design system support"]
    },
    {
        "id": 6611,
        "name": "lobe-tts",
        "llm_relevance_score": 82,
        "llm_summary": "Text-to-speech library for LobeHub enabling voice synthesis capabilities for conversational agents and voice interfaces.",
        "llm_category": "agent_skill",
        "llm_key_features": ["Text-to-speech synthesis", "Multiple voice providers", "Streaming audio support", "Agent voice capabilities"]
    }
]

conn = sqlite3.connect('/home/ubuntu/.openclaw/workspace/rosclaw_crawler/rosclaw_hub.db')
cursor = conn.cursor()

now = datetime.utcnow().isoformat()
model = 'kimi-k2p5-agent'

for analysis in analyses:
    cursor.execute('''
        UPDATE rosclaw_hub_resources 
        SET llm_relevance_score = ?,
            llm_summary = ?,
            llm_category = ?,
            llm_key_features = ?,
            llm_analyzed_at = ?,
            llm_model = ?
        WHERE id = ?
    ''', (
        analysis['llm_relevance_score'],
        analysis['llm_summary'],
        analysis['llm_category'],
        json.dumps(analysis['llm_key_features']),
        now,
        model,
        analysis['id']
    ))
    print(f"✅ Updated {analysis['name']}: score={analysis['llm_relevance_score']}, category={analysis['llm_category']}")

conn.commit()

# Check remaining
cursor.execute('SELECT COUNT(*) FROM rosclaw_hub_resources WHERE is_relevant=1 AND llm_analyzed_at IS NULL')
remaining = cursor.fetchone()[0]
print(f"\n📊 Batch complete: {len(analyses)} analyzed")
print(f"📈 Scores: {[a['llm_relevance_score'] for a in analyses]}")
print(f"⏳ Remaining unanalyzed: {remaining}")

conn.close()
