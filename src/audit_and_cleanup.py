#!/usr/bin/env python3
"""
ROSClaw Hub Audit & Cleanup Tool

1. Fetches all items from rosclaw.io (skills + mcps)
2. Applies strict filtering rules
3. Generates audit report
4. Optionally deletes non-compliant items

Usage:
    python3 audit_and_cleanup.py --audit-only    # Just generate report
    python3 audit_and_cleanup.py --execute       # Actually delete items
"""

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime
from urllib.parse import urlparse

from strict_rosclaw_filter import strict_classify

BASE_URL = 'https://www.rosclaw.io'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.rosclaw.io/hub',
}


def fetch_all_items(endpoint_name: str) -> list:
    """Fetch all items from an API endpoint"""
    all_items = []
    page = 1
    endpoint = f'{BASE_URL}/api/{endpoint_name}'

    print(f"\n📡 Fetching {endpoint_name}...")
    while True:
        req = urllib.request.Request(
            f"{endpoint}?page={page}&limit=100",
            headers=HEADERS
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if not data or not isinstance(data, list) or len(data) == 0:
                    break
                all_items.extend(data)
                print(f"  Page {page}: +{len(data)} items (total: {len(all_items)})")
                if len(data) < 100:
                    break
                page += 1
                time.sleep(0.3)
        except Exception as e:
            print(f"  ⚠️ Error on page {page}: {e}")
            break

    return all_items


def audit_items(items: list, item_type: str) -> dict:
    """Audit items against strict criteria"""
    results = {'keep': [], 'remove': [], 'review': []}

    print(f"\n🔍 Auditing {len(items)} {item_type} items...")
    for i, item in enumerate(items, 1):
        name = item.get('name', '')
        desc = item.get('description', '')
        url = item.get('githubRepoUrl', '')

        decision, reason, confidence = strict_classify(name, desc, url)

        result = {
            'id': item.get('id'),
            'name': name,
            'displayName': item.get('displayName', ''),
            'description': desc,
            'url': url,
            'category': item.get('category', ''),
            'stars': item.get('githubStars', 0),
            'tags': item.get('tags', []),
            '_decision': decision,
            '_reason': reason,
            '_confidence': confidence,
        }
        results[decision].append(result)

        if i % 50 == 0:
            print(f"  Processed {i}/{len(items)}...")

    return results


def print_audit_report(skills_audit: dict, mcps_audit: dict):
    """Print formatted audit report"""
    print("\n" + "=" * 80)
    print("ROSClaw Hub Audit Report")
    print("=" * 80)

    for item_type, audit in [('SKILLS', skills_audit), ('MCPS', mcps_audit)]:
        total = sum(len(v) for v in audit.values())
        print(f"\n📦 {item_type}: {total} total")
        print(f"  ✅ KEEP:    {len(audit['keep'])} ({len(audit['keep'])/total*100:.1f}%)")
        print(f"  ❌ REMOVE:  {len(audit['remove'])} ({len(audit['remove'])/total*100:.1f}%)")
        print(f"  ⚠️  REVIEW:  {len(audit['review'])} ({len(audit['review'])/total*100:.1f}%)")

        print(f"\n--- {item_type} to KEEP ({len(audit['keep'])}) ---")
        for item in audit['keep']:
            print(f"  ✅ {item['name']} | {item['category']} | {item['stars']}⭐")
            print(f"     Reason: {item['_reason']}")

        print(f"\n--- {item_type} to REMOVE ({len(audit['remove'])}) ---")
        for item in audit['remove'][:20]:
            print(f"  ❌ {item['name']} | {item['category']} | {item['stars']}⭐")
            print(f"     Reason: {item['_reason']}")
        if len(audit['remove']) > 20:
            print(f"     ... and {len(audit['remove']) - 20} more")

        print(f"\n--- {item_type} to REVIEW ({len(audit['review'])}) ---")
        for item in audit['review']:
            print(f"  ⚠️  {item['name']} | {item['category']} | {item['stars']}⭐")
            print(f"     Reason: {item['_reason']}")


def delete_item(item_id: str, endpoint: str) -> tuple:
    """Delete an item from the site"""
    # Note: This requires admin API key which we don't have
    # We'll document the IDs to delete instead
    return True, "Documented for manual deletion"


def save_report(skills_audit: dict, mcps_audit: dict):
    """Save audit report to JSON"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report = {
        'timestamp': timestamp,
        'skills': {
            'keep': skills_audit['keep'],
            'remove': skills_audit['remove'],
            'review': skills_audit['review'],
        },
        'mcps': {
            'keep': mcps_audit['keep'],
            'remove': mcps_audit['remove'],
            'review': mcps_audit['review'],
        }
    }

    filename = f'/home/ubuntu/rosclaw/rosclaw_crawler/audit_report_{timestamp}.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Audit report saved: {filename}")
    return filename


def main():
    parser = argparse.ArgumentParser(description='ROSClaw Hub Audit & Cleanup')
    parser.add_argument('--audit-only', action='store_true', help='Only generate audit report')
    parser.add_argument('--execute', action='store_true', help='Execute deletions (requires admin key)')
    args = parser.parse_args()

    print("=" * 80)
    print("ROSClaw Hub Audit & Cleanup Tool")
    print("=" * 80)

    # Fetch all items
    skills = fetch_all_items('skills')
    mcps = fetch_all_items('mcp-packages')

    # Audit
    skills_audit = audit_items(skills, 'skill')
    mcps_audit = audit_items(mcps, 'mcp')

    # Report
    print_audit_report(skills_audit, mcps_audit)

    # Save report
    report_file = save_report(skills_audit, mcps_audit)

    # Generate deletion list
    print("\n" + "=" * 80)
    print("Deletion Summary")
    print("=" * 80)

    all_remove = skills_audit['remove'] + mcps_audit['remove']
    print(f"\nTotal items to remove: {len(all_remove)}")
    print("\nIDs to delete:")
    for item in all_remove:
        print(f"  {item['id']} | {item['name']}")

    if args.execute:
        print("\n⚠️  Execute mode not yet implemented - requires admin API key")
        print("   Please use the IDs above to delete manually or implement API deletion")

    print("\n" + "=" * 80)
    print("Audit Complete")
    print("=" * 80)


if __name__ == '__main__':
    main()
