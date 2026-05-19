#!/usr/bin/env python3
"""
Upload approved items to rosclaw.io
"""

import json
import urllib.request
import sqlite3
import sys
import os

API_KEY = "os.getenv("ROSCALW_API_KEY", "")"
BASE_URL = "https://www.rosclaw.io"

HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY,
}


def upload_skill(name, description, url, stars):
    """Upload a skill to the site."""
    # Parse owner/repo from URL
    parts = url.replace('https://github.com/', '').split('/')
    owner = parts[0] if len(parts) > 0 else 'unknown'
    repo = parts[1] if len(parts) > 1 else name
    
    data = json.dumps({
        "name": repo,
        "display_name": repo.replace('-', ' ').replace('_', ' ').title(),
        "author_name": owner,
        "description": description or f"Agent skill for {name}",
        "url": url,
        "stars": stars,
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
        return False, f"HTTP {e.code}: {e.read().decode()}"
    except Exception as e:
        return False, str(e)


def upload_mcp(name, description, url, stars):
    """Upload an MCP to the site."""
    # Parse owner/repo from URL
    parts = url.replace('https://github.com/', '').split('/')
    owner = parts[0] if len(parts) > 0 else 'unknown'
    repo = parts[1] if len(parts) > 1 else name
    
    data = json.dumps({
        "name": repo,
        "display_name": repo.replace('-', ' ').replace('_', ' ').title(),
        "author_name": owner,
        "description": description or f"MCP server for {name}",
        "url": url,
        "stars": stars,
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
        return False, f"HTTP {e.code}: {e.read().decode()}"
    except Exception as e:
        return False, str(e)


def main():
    conn = sqlite3.connect('/home/ubuntu/rosclaw/rosclaw_crawler/data/rosclaw_hub.db')
    c = conn.cursor()

    print("=" * 70)
    print("UPLOADING APPROVED ITEMS TO ROSCLAW.IO")
    print("=" * 70)

    # Upload skills
    c.execute("SELECT full_name, description, url, stars FROM skills WHERE decision='keep' AND site_status='pending'")
    skills = c.fetchall()
    print(f"\nUploading {len(skills)} skills...")

    success_count = 0
    for name, desc, url, stars in skills:
        print(f"  Uploading {name}...", end=" ")
        ok, result = upload_skill(name, desc, url, stars)
        if ok:
            print("✅")
            c.execute("UPDATE skills SET site_status='uploaded' WHERE full_name=?", (name,))
            success_count += 1
        else:
            print(f"❌ {result}")

    # Upload MCPs
    c.execute("SELECT full_name, description, url, stars FROM mcps WHERE decision='keep' AND site_status='pending'")
    mcps = c.fetchall()
    print(f"\nUploading {len(mcps)} MCPs...")

    mcp_success = 0
    for name, desc, url, stars in mcps:
        print(f"  Uploading {name}...", end=" ")
        ok, result = upload_mcp(name, desc, url, stars)
        if ok:
            print("✅")
            c.execute("UPDATE mcps SET site_status='uploaded' WHERE full_name=?", (name,))
            mcp_success += 1
        else:
            print(f"❌ {result}")

    conn.commit()
    conn.close()

    print(f"\n{'=' * 70}")
    print(f"UPLOAD COMPLETE")
    print(f"  Skills: {success_count}/{len(skills)} uploaded")
    print(f"  MCPs: {mcp_success}/{len(mcps)} uploaded")
    print(f"  Total: {success_count + mcp_success}/{len(skills) + len(mcps)}")


if __name__ == "__main__":
    main()
