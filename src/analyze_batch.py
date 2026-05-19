import sqlite3
import os
from datetime import datetime, timezone

db_path = os.path.expanduser('~/.openclaw/workspace/rosclaw_crawler/rosclaw_hub.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute('SELECT id, name FROM rosclaw_hub_resources WHERE is_relevant=1 AND llm_analyzed_at IS NULL ORDER BY id LIMIT 5')
rows = cursor.fetchall()

analyses = {
    6752: {"score": 85, "summary": "MCP server for Sweeppea platform integration with agent workflows.", "category": "mcp_server", "features": "MCP protocol,Sweeppea integration,Development workflow,Agent tooling"},
    6753: {"score": 75, "summary": "MCP server for BYOK observability and telemetry data access.", "category": "mcp_server", "features": "Observability integration,Telemetry access,Monitoring,MCP protocol"},
    6754: {"score": 70, "summary": "MCP server for Framedeck platform deck-based workflow management.", "category": "mcp_server", "features": "Framedeck integration,Deck management,Workflow automation,MCP server"},
    6755: {"score": 80, "summary": "MCP server with ACT action chunking for embodied AI execution.", "category": "mcp_server", "features": "ACT action chunking,Embodied AI support,Action execution,MCP protocol"},
    6756: {"score": 72, "summary": "MCP server for IP geolocation and WHOIS domain lookup services.", "category": "mcp_server", "features": "IP geolocation,WHOIS lookup,Domain intelligence,MCP server"}
}

now = datetime.now(timezone.utc).isoformat()
model = "kimi-k2p5-agent"

for row in rows:
    a = analyses[row['id']]
    cursor.execute('''
        UPDATE rosclaw_hub_resources 
        SET llm_relevance_score = ?, llm_summary = ?, llm_category = ?, llm_key_features = ?, llm_analyzed_at = ?, llm_model = ?
        WHERE id = ?
    ''', (a["score"], a["summary"], a["category"], a["features"], now, model, row['id']))
    print(f"Updated ID {row['id']}: {row['name']} - Score: {a['score']}")

conn.commit()
conn.close()
print(f"\nBatch complete: {len(rows)} repos analyzed")
