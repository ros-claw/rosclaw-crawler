#!/usr/bin/env python3
"""
ROSClaw Site Cleanup - Delete non-compliant items

This script deletes items from rosclaw.io that don't meet the strict criteria.
Requires admin API key.

Usage:
    python3 delete_from_site.py --dry-run    # Preview what would be deleted
    python3 delete_from_site.py --execute    # Actually delete (requires confirmation)
"""

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime

from strict_rosclaw_filter import strict_classify
import os

BASE_URL = 'https://www.rosclaw.io'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.rosclaw.io/hub',
}

# NOTE: Replace with actual admin API key
ADMIN_API_KEY = os.getenv("ROSCALW_API_KEY", "")


def fetch_all(endpoint_name: str) -> list:
    """Fetch all items from an API endpoint"""
    all_items = []
    page = 1
    endpoint = f'{BASE_URL}/api/{endpoint_name}'
    while True:
        req = urllib.request.Request(f"{endpoint}?page={page}&limit=100", headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if not data or not isinstance(data, list) or len(data) == 0:
                    break
                all_items.extend(data)
                if len(data) < 100:
                    break
                page += 1
        except Exception as e:
            print(f"Error on page {page}: {e}")
            break
    return all_items


def delete_item(item_id: str, endpoint: str) -> tuple:
    """Delete an item via API"""
    delete_headers = {
        'Content-Type': 'application/json',
        'X-API-Key': ADMIN_API_KEY,
    }
    delete_url = f"{BASE_URL}/api/{endpoint}?id={item_id}"
    req = urllib.request.Request(delete_url, headers=delete_headers, method='DELETE')
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return True, "Already deleted (404)"
        return False, f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description='ROSClaw Site Cleanup')
    parser.add_argument('--dry-run', action='store_true', help='Preview only')
    parser.add_argument('--execute', action='store_true', help='Execute deletions')
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("Please specify --dry-run or --execute")
        sys.exit(1)

    print("=" * 80)
    print("ROSClaw Site Cleanup")
    print("=" * 80)

    # Fetch
    print("\n📡 Fetching skills...")
    skills = fetch_all('skills')
    print(f"   Got {len(skills)} skills")

    print("\n📡 Fetching MCPs...")
    mcps = fetch_all('mcp-packages')
    print(f"   Got {len(mcps)} mcps")

    # Audit
    to_delete = []

    for item in skills:
        d, r, c = strict_classify(item['name'], item.get('description', ''), item.get('githubRepoUrl', ''))
        if d == 'remove':
            to_delete.append({'id': item['id'], 'name': item['name'], 'type': 'skill', 'reason': r})

    for item in mcps:
        d, r, c = strict_classify(item['name'], item.get('description', ''), item.get('githubRepoUrl', ''))
        if d == 'remove':
            to_delete.append({'id': item['id'], 'name': item['name'], 'type': 'mcp', 'reason': r})

    print(f"\n🔍 Audit complete: {len(to_delete)} items to delete")

    if args.dry_run:
        print("\n--- DRY RUN: Items that would be deleted ---")
        for item in to_delete:
            print(f"  ❌ [{item['type']}] {item['name']}")
            print(f"     Reason: {item['reason']}")
            print(f"     ID: {item['id']}")
        print(f"\nTotal: {len(to_delete)} items would be deleted")
        return

    if args.execute:
        print("\n⚠️  EXECUTE MODE")
        print(f"About to delete {len(to_delete)} items from rosclaw.io")
        confirm = input("Type 'DELETE' to confirm: ")
        if confirm != 'DELETE':
            print("Aborted.")
            return

        success_count = 0
        fail_count = 0
        results = []

        for i, item in enumerate(to_delete, 1):
            print(f"\n[{i}/{len(to_delete)}] Deleting {item['type']}: {item['name']}")
            endpoint = 'skills' if item['type'] == 'skill' else 'mcp-packages'
            success, msg = delete_item(item['id'], endpoint)

            if success:
                success_count += 1
                print(f"  ✅ {msg}")
            else:
                fail_count += 1
                print(f"  ❌ {msg}")

            results.append({
                'name': item['name'],
                'id': item['id'],
                'type': item['type'],
                'success': success,
                'message': msg,
            })
            time.sleep(0.5)

        # Save log
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log = {
            'timestamp': timestamp,
            'total': len(to_delete),
            'success': success_count,
            'failed': fail_count,
            'results': results,
        }
        log_file = f'/home/ubuntu/rosclaw/rosclaw_crawler/deletion_log_{timestamp}.json'
        with open(log_file, 'w') as f:
            json.dump(log, f, ensure_ascii=False, indent=2)

        print("\n" + "=" * 80)
        print("Deletion Complete")
        print("=" * 80)
        print(f"Total: {len(to_delete)}")
        print(f"Success: {success_count}")
        print(f"Failed: {fail_count}")
        print(f"Log: {log_file}")


if __name__ == '__main__':
    main()
