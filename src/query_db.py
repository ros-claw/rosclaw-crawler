#!/usr/bin/env python3
"""
Query the local database.
"""

import sys
import json
sys.path.insert(0, '/home/ubuntu/rosclaw/rosclaw_crawler/src')
from database import get_items, get_stats

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Query rosclaw database')
    parser.add_argument('--type', choices=['skill', 'mcp'], required=True)
    parser.add_argument('--decision', choices=['keep', 'remove', 'review', 'pending'])
    parser.add_argument('--status', choices=['pending', 'uploaded', 'deleted', 'skipped'])
    parser.add_argument('--limit', type=int, default=50)
    parser.add_argument('--stats', action='store_true', help='Show only stats')
    args = parser.parse_args()

    if args.stats:
        print(json.dumps(get_stats(), indent=2))
        return

    items = get_items(args.type, decision=args.decision, site_status=args.status, limit=args.limit)
    print(f"Found {len(items)} {args.type}s")
    for item in items:
        print(f"\n{'='*60}")
        print(f"Name: {item['full_name']}")
        print(f"Decision: {item['decision']} (confidence: {item['confidence']})")
        print(f"Reason: {item['reason']}")
        print(f"Stars: {item['stars']} | Lang: {item['language']}")
        print(f"Site Status: {item['site_status']} | ID: {item['site_id']}")
        print(f"URL: {item['url']}")
        print(f"First seen: {item['first_seen']}")

if __name__ == '__main__':
    main()
