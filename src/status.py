"""Quick status check for the ROSClaw Crawler."""
import json
import sqlite3
import os
import subprocess

def main():
    conn = sqlite3.connect('rosclaw_hub.db')
    c = conn.cursor()

    c.execute('SELECT COUNT(*) FROM rosclaw_hub_resources')
    total = c.fetchone()[0]

    c.execute("SELECT type, COUNT(*) FROM rosclaw_hub_resources GROUP BY type")
    by_type = dict(c.fetchall())

    c.execute('SELECT COUNT(*) FROM rosclaw_hub_resources WHERE is_embodied = 1')
    embodied = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM rosclaw_hub_resources WHERE is_relevant = 0')
    irrelevant = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM rosclaw_hub_resources WHERE is_relevant = 1 OR is_relevant IS NULL')
    relevant = c.fetchone()[0]

    c.execute("""
        SELECT source, COUNT(*) FROM rosclaw_hub_resources
        GROUP BY source ORDER BY COUNT(*) DESC LIMIT 8
    """)
    top_sources = c.fetchall()

    c.execute("""
        SELECT name, type, stars, is_embodied, repo_url
        FROM rosclaw_hub_resources
        ORDER BY stars DESC LIMIT 10
    """)
    top10 = c.fetchall()

    c.execute("""
        SELECT name, type, stars, domain_tags, repo_url
        FROM rosclaw_hub_resources
        WHERE is_embodied = 1
        ORDER BY stars DESC LIMIT 10
    """)
    top_embodied = c.fetchall()

    conn.close()

    print("=" * 60)
    print("ROSCLAW CRAWLER STATUS")
    print("=" * 60)
    print(f"Total records:     {total}")
    print(f"Agent Skills:      {by_type.get('agent_skill', 0)}")
    print(f"MCP Servers:       {by_type.get('mcp_server', 0)}")
    print(f"Embodied/Physical: {embodied}")
    print(f"Relevant:          {relevant}")
    print(f"Filtered out:      {irrelevant}")
    print()
    print("Top Sources:")
    for src, cnt in top_sources:
        print(f"  {cnt:4d} | {src}")
    print()
    print("Top 10 Overall by Stars:")
    for r in top10:
        mark = "🤖" if r[3] else "  "
        print(f"  {r[2]:6d} ⭐ {mark} [{r[1]}] {r[0]}")
    print()
    print("Top 10 Embodied AI by Stars:")
    for r in top_embodied:
        tags_short = ''
        if r[3]:
            try:
                tags_list = json.loads(r[3])
                tags_short = ', '.join(str(t) for t in tags_list[:5])
            except Exception:
                tags_short = str(r[3])[:30]
        print(f"  {r[2]:6d} ⭐ [{r[1]}] {r[0]} | tags: {tags_short}")
    print("=" * 60)

    daemon_running = os.system("pgrep -f continuous_crawler.py > /dev/null") == 0
    print(f"24/7 Daemon running: {'YES ✅' if daemon_running else 'NO ❌'}")
    if daemon_running and os.path.exists('/tmp/rosclaw_continuous.log'):
        lines = subprocess.getoutput('wc -l /tmp/rosclaw_continuous.log').split()[0]
        tail = subprocess.getoutput('tail -8 /tmp/rosclaw_continuous.log')
        print(f"Log lines: {lines}")
        print("Last 8 log lines:")
        for line in tail.split('\n'):
            print(f"  {line}")

if __name__ == '__main__':
    main()
