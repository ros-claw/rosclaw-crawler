#!/usr/bin/env python3
"""
Sync site items and crawl results to local database.
"""

import json
import sys
import urllib.request
sys.path.insert(0, '/home/ubuntu/rosclaw/rosclaw_crawler/src')
from database import insert_item, update_site_state, get_stats
from crawler_v2 import strict_classify

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.rosclaw.io/hub',
}


def sync_site_items(item_type):
    """Fetch all items from site and sync to DB."""
    items = []
    page = 1
    while True:
        endpoint = 'skills' if item_type == 'skill' else 'mcp-packages'
        url = f'https://www.rosclaw.io/api/{endpoint}?page={page}&limit=100'
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                page_items = data if isinstance(data, list) else data.get('items', data.get('data', []))
                if not page_items:
                    break
                items.extend(page_items)
                if len(page_items) < 100:
                    break
                page += 1
        except Exception as e:
            print(f"Error page {page}: {e}")
            break

    print(f"Fetched {len(items)} {item_type}s from site")

    for item in items:
        name = item.get('name', '')
        desc = item.get('description', '') or ''
        url = item.get('githubRepoUrl', '') or item.get('url', '')

        decision, reason, confidence = strict_classify(name, desc, url)

        db_item = {
            'source': 'site',
            'name': name.split('/')[-1] if '/' in name else name,
            'full_name': name,
            'description': desc,
            'url': url,
            'stars': item.get('stars', 0),
            'language': item.get('language', ''),
            'topics': item.get('topics', []),
            'decision': decision,
            'reason': reason,
            'confidence': confidence,
            'site_id': item.get('id', ''),
            'site_status': 'uploaded',
            'raw_data': item,
        }
        insert_item(item_type, db_item)

    return len(items)


def sync_crawl_results(results_file, item_type='mcp'):
    """Sync crawler JSON results to DB."""
    with open(results_file) as f:
        results = json.load(f)

    kept = results.get('keep', [])
    removed = results.get('remove', [])

    for item in kept + removed:
        db_item = {
            'source': 'github',
            'name': item.get('name', '').split('/')[-1] if '/' in item.get('name', '') else item.get('name', ''),
            'full_name': item.get('name', ''),
            'description': item.get('description', ''),
            'url': item.get('url', ''),
            'stars': item.get('stars', 0),
            'language': item.get('language', ''),
            'topics': item.get('topics', []),
            'decision': item.get('decision', 'pending'),
            'reason': item.get('reason', ''),
            'confidence': item.get('confidence', 0),
            'site_status': 'pending',
            'raw_data': item,
        }
        insert_item(item_type, db_item)

    print(f"Synced {len(kept)} kept + {len(removed)} removed = {len(kept)+len(removed)} {item_type}s from crawl")
    return len(kept) + len(removed)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--site', action='store_true', help='Sync from site')
    parser.add_argument('--crawl-file', help='Sync from crawl JSON file')
    parser.add_argument('--type', choices=['skill', 'mcp'], default='mcp')
    args = parser.parse_args()

    if args.site:
        print("Syncing site items to DB...")
        skill_count = sync_site_items('skill')
        mcp_count = sync_site_items('mcp')
        total = skill_count + mcp_count
        quality = 100.0  # After cleanup
        update_site_state(skill_count, mcp_count, quality)
        print(f"Done! Skills: {skill_count}, MCPs: {mcp_count}")

    if args.crawl_file:
        print(f"Syncing crawl results from {args.crawl_file}...")
        sync_crawl_results(args.crawl_file, args.type)

    print("\nCurrent DB stats:")
    print(json.dumps(get_stats(), indent=2))


if __name__ == '__main__':
    main()
