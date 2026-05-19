#!/usr/bin/env python3
"""
Site Cleanup Tool - Remove irrelevant skills and MCPs from rosclaw.io

Usage:
    python3 site_cleanup.py --dry-run          # Preview what would be deleted
    python3 site_cleanup.py --execute          # Actually delete (requires API key)
    python3 site_cleanup.py --list-keep        # List items to keep
"""

import json
import sys
import urllib.request
import urllib.error
import argparse
from datetime import datetime

sys.path.insert(0, '/home/ubuntu/rosclaw/rosclaw_crawler/src')
from crawler_v2 import strict_classify

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.rosclaw.io/hub',
}

API_BASE = 'https://www.rosclaw.io/api'


def fetch_all_items(item_type: str) -> list[dict]:
    """Fetch all items from the site API."""
    items = []
    page = 1
    limit = 100

    while True:
        url = f"{API_BASE}/{item_type}?page={page}&limit={limit}"
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                page_items = data if isinstance(data, list) else data.get('items', data.get('data', []))
                if not page_items:
                    break
                items.extend(page_items)
                if len(page_items) < limit:
                    break
                page += 1
        except Exception as e:
            print(f"Error fetching {item_type} page {page}: {e}")
            break

    return items


def classify_items(items: list[dict], item_type: str) -> dict:
    """Classify items into keep/remove/review."""
    result = {
        'keep': [],
        'remove': [],
        'review': [],
    }

    for item in items:
        name = item.get('name', '')
        desc = item.get('description', '') or ''
        url = item.get('githubRepoUrl', '') or item.get('url', '')

        decision, reason, confidence = strict_classify(name, desc, url)

        entry = {
            'id': item.get('id', ''),
            'name': name,
            'description': desc[:200],
            'decision': decision,
            'reason': reason,
            'confidence': confidence,
        }

        result[decision].append(entry)

    return result


def delete_item(item_type: str, item_id: str, api_key: str, dry_run: bool = True) -> dict:
    """Delete an item from the site."""
    endpoint = 'skills' if item_type == 'skill' else 'mcp-packages'
    url = f"{API_BASE}/{endpoint}/{item_id}"

    if dry_run:
        return {'success': True, 'dry_run': True, 'url': url}

    headers = {**HEADERS, 'X-API-Key': api_key}
    req = urllib.request.Request(url, headers=headers, method='DELETE')

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {'success': True, 'status': resp.status, 'dry_run': False}
    except urllib.error.HTTPError as e:
        return {'success': False, 'status': e.code, 'error': e.reason}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def main():
    parser = argparse.ArgumentParser(description='Clean up rosclaw.io site')
    parser.add_argument('--dry-run', action='store_true', help='Preview deletions')
    parser.add_argument('--execute', action='store_true', help='Actually delete')
    parser.add_argument('--list-keep', action='store_true', help='List items to keep')
    parser.add_argument('--api-key', help='Admin API key for deletion')
    parser.add_argument('--type', choices=['skill', 'mcp', 'all'], default='all',
                        help='Item type to process')
    args = parser.parse_args()

    if args.execute and not args.api_key:
        print("ERROR: --execute requires --api-key")
        sys.exit(1)

    print("="*70)
    print("Rosclaw.io Site Cleanup Tool")
    print("="*70)

    # Fetch items
    all_items = {}
    if args.type in ('skill', 'all'):
        print("\n[1/4] Fetching skills...")
        skills = fetch_all_items('skills')
        print(f"      Found {len(skills)} skills")
        all_items['skill'] = skills

    if args.type in ('mcp', 'all'):
        print("\n[2/4] Fetching MCPs...")
        mcps = fetch_all_items('mcp-packages')
        print(f"      Found {len(mcps)} MCPs")
        all_items['mcp'] = mcps

    # Classify
    print("\n[3/4] Classifying items...")
    classifications = {}
    for item_type, items in all_items.items():
        classifications[item_type] = classify_items(items, item_type)

    # Print summary
    print("\n" + "="*70)
    print("CLASSIFICATION SUMMARY")
    print("="*70)
    total_keep = 0
    total_remove = 0
    total_review = 0

    for item_type, result in classifications.items():
        keep = len(result['keep'])
        remove = len(result['remove'])
        review = len(result['review'])
        total = keep + remove + review
        total_keep += keep
        total_remove += remove
        total_review += review

        print(f"\n{item_type.upper()}S: {total} total")
        print(f"  ✅ Keep:    {keep} ({keep/total*100:.1f}%)")
        print(f"  ❌ Remove:  {remove} ({remove/total*100:.1f}%)")
        print(f"  ⚠️  Review:  {review} ({review/total*100:.1f}%)")

    print(f"\nTOTAL: {total_keep + total_remove + total_review}")
    print(f"  ✅ Keep: {total_keep}")
    print(f"  ❌ Remove: {total_remove}")
    print(f"  ⚠️  Review: {total_review}")

    # List items to keep
    if args.list_keep:
        print("\n" + "="*70)
        print("ITEMS TO KEEP")
        print("="*70)
        for item_type, result in classifications.items():
            if result['keep']:
                print(f"\n{item_type.upper()}S:")
                for item in result['keep']:
                    print(f"  ✅ {item['name']}")
                    print(f"     Reason: {item['reason']}")

    # List items to remove
    print("\n" + "="*70)
    print("ITEMS TO REMOVE")
    print("="*70)
    for item_type, result in classifications.items():
        if result['remove']:
            print(f"\n{item_type.upper()}S:")
            for item in result['remove']:
                print(f"  ❌ {item['name']}")
                print(f"     Reason: {item['reason']}")
                print(f"     ID: {item['id']}")

    # Execute deletions
    if args.execute:
        print("\n" + "="*70)
        print("EXECUTING DELETIONS")
        print("="*70)

        deleted = 0
        failed = 0

        for item_type, result in classifications.items():
            for item in result['remove']:
                print(f"\nDeleting {item_type}: {item['name']}...")
                resp = delete_item(item_type, item['id'], args.api_key, dry_run=False)
                if resp['success']:
                    print(f"  ✅ Deleted")
                    deleted += 1
                else:
                    print(f"  ❌ Failed: {resp.get('status', '')} {resp.get('error', '')}")
                    failed += 1

        print(f"\n{'='*70}")
        print(f"Done! Deleted: {deleted}, Failed: {failed}")

    # Save report
    report = {
        'timestamp': datetime.now().isoformat(),
        'classifications': classifications,
        'summary': {
            'total_keep': total_keep,
            'total_remove': total_remove,
            'total_review': total_review,
        }
    }

    report_file = f'cleanup_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(report_file, 'w') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nReport saved to: {report_file}")


if __name__ == '__main__':
    main()
