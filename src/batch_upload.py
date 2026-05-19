#!/usr/bin/env python3
"""
Batch upload items to rosclaw.io with proper headers to bypass Cloudflare
"""

import json
import urllib.request
import sqlite3
import time
import os

API_KEY = os.getenv("ROSCALW_API_KEY", "")
BASE_URL = 'https://www.rosclaw.io'

HEADERS = {
    'x-api-key': API_KEY,
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Origin': 'https://www.rosclaw.io',
    'Referer': 'https://www.rosclaw.io/',
}


def upload_skill(name, display_name, description, url, author_name, stars=0):
    data = json.dumps({
        "name": name,
        "display_name": display_name,
        "description": description or f"Agent skill for {name}",
        "github_repo_url": url,
        "author_name": author_name,
    }).encode()

    req = urllib.request.Request(
        f"{BASE_URL}/api/skills",
        data=data,
        headers=HEADERS,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return True, result
    except urllib.error.HTTPError as e:
        if e.code == 409:
            return True, {"message": "Already exists"}
        return False, f"HTTP {e.code}: {e.read().decode()}"
    except Exception as e:
        return False, str(e)


def upload_mcp(name, description, url, author_name, stars=0):
    data = json.dumps({
        "name": name,
        "description": description or f"MCP server for {name}",
        "github_repo_url": url,
        "author_name": author_name,
        "category": "mcp_package",
        "robot_type": "universal",
        "tags": ["mcp", "robotics"],
    }).encode()

    req = urllib.request.Request(
        f"{BASE_URL}/api/mcp-packages",
        data=data,
        headers=HEADERS,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return True, result
    except urllib.error.HTTPError as e:
        if e.code == 409:
            return True, {"message": "Already exists"}
        return False, f"HTTP {e.code}: {e.read().decode()}"
    except Exception as e:
        return False, str(e)


def main():
    conn = sqlite3.connect('/home/ubuntu/rosclaw/rosclaw_crawler/data/rosclaw_hub.db')
    c = conn.cursor()

    print("=" * 70)
    print("BATCH UPLOAD TO ROSCLAW.IO")
    print("=" * 70)

    # Upload skills
    c.execute("SELECT full_name, description, url, stars FROM skills WHERE decision='keep' AND site_status='pending'")
    skills = c.fetchall()
    print(f"\nUploading {len(skills)} skills...")

    success = 0
    for name, desc, url, stars in skills:
        parts = name.split('/', 1)
        owner = parts[0]
        repo = parts[1] if len(parts) > 1 else name
        display_name = repo.replace('-', ' ').replace('_', ' ').title()

        print(f"  {name}...", end=" ", flush=True)
        ok, result = upload_skill(name, display_name, desc, url, owner, stars)
        if ok:
            print("✅")
            c.execute("UPDATE skills SET site_status='uploaded' WHERE full_name=?", (name,))
            success += 1
        else:
            print(f"❌ {result}")
        time.sleep(0.5)

    # Upload MCPs
    c.execute("SELECT full_name, description, url, stars FROM mcps WHERE decision='keep' AND site_status='pending'")
    mcps = c.fetchall()
    print(f"\nUploading {len(mcps)} MCPs...")

    mcp_success = 0
    for name, desc, url, stars in mcps:
        parts = name.split('/', 1)
        owner = parts[0]

        print(f"  {name}...", end=" ", flush=True)
        ok, result = upload_mcp(name, desc, url, owner, stars)
        if ok:
            print("✅")
            c.execute("UPDATE mcps SET site_status='uploaded' WHERE full_name=?", (name,))
            mcp_success += 1
        else:
            print(f"❌ {result}")
        time.sleep(0.5)

    conn.commit()
    conn.close()

    print(f"\n{'=' * 70}")
    print(f"UPLOAD COMPLETE")
    print(f"  Skills: {success}/{len(skills)}")
    print(f"  MCPs: {mcp_success}/{len(mcps)}")
    print(f"  Total: {success + mcp_success}/{len(skills) + len(mcps)}")


if __name__ == "__main__":
    main()
