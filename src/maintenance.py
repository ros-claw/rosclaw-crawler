#!/usr/bin/env python3
"""
Rosclaw Maintenance Tool

Runs daily/weekly to:
1. Audit existing site items for quality
2. Crawl GitHub for new high-quality MCPs and Skills
3. Generate reports

Usage:
    python3 maintenance.py --audit          # Audit existing items
    python3 maintenance.py --crawl          # Crawl GitHub for new items
    python3 maintenance.py --full           # Audit + Crawl + Report
"""

import json
import sys
import urllib.request
from datetime import datetime

sys.path.insert(0, '/home/ubuntu/rosclaw/rosclaw_crawler/src')
from crawler_v2 import strict_classify, run_crawler, save_results
from site_cleanup import fetch_all_items, classify_items

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.rosclaw.io/hub',
}


def audit_site():
    """Audit all items currently on the site."""
    print("="*70)
    print("AUDITING SITE")
    print("="*70)

    skills = fetch_all_items('skills')
    mcps = fetch_all_items('mcp-packages')

    skill_result = classify_items(skills, 'skill')
    mcp_result = classify_items(mcps, 'mcp')

    total_keep = len(skill_result['keep']) + len(mcp_result['keep'])
    total_remove = len(skill_result['remove']) + len(mcp_result['remove'])
    total_review = len(skill_result['review']) + len(mcp_result['review'])

    print(f"\nSkills: {len(skills)} total")
    print(f"  Keep: {len(skill_result['keep'])} | Remove: {len(skill_result['remove'])} | Review: {len(skill_result['review'])}")

    print(f"\nMCPs: {len(mcps)} total")
    print(f"  Keep: {len(mcp_result['keep'])} | Remove: {len(mcp_result['remove'])} | Review: {len(mcp_result['review'])}")

    if total_remove > 0:
        print(f"\n⚠️  WARNING: {total_remove} items should be removed!")
        print("   Run: python3 src/site_cleanup.py --execute --api-key YOUR_KEY")

    return {
        'timestamp': datetime.now().isoformat(),
        'skills': skill_result,
        'mcps': mcp_result,
        'summary': {
            'total_keep': total_keep,
            'total_remove': total_remove,
            'total_review': total_review,
        }
    }


def crawl_new(github_token=None):
    """Crawl GitHub for new high-quality items."""
    print("\n" + "="*70)
    print("CRAWLING GITHUB FOR NEW ITEMS")
    print("="*70)

    results = run_crawler(github_token=github_token, max_results_per_query=10)
    output_path = save_results(results)

    print(f"\nNew items found: {len(results['keep'])}")
    for item in results['keep']:
        print(f"  + {item['name']} ({item['stars']} stars)")
        print(f"    {item['url']}")

    return results, output_path


def generate_report(audit_data, crawl_data=None, output_path='maintenance_report.json'):
    """Generate a comprehensive maintenance report."""
    report = {
        'timestamp': datetime.now().isoformat(),
        'audit': audit_data,
    }
    if crawl_data:
        report['crawl'] = {
            'stats': crawl_data['stats'],
            'new_items': crawl_data['keep'],
        }

    with open(output_path, 'w') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\nReport saved to: {output_path}")
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Rosclaw Maintenance Tool')
    parser.add_argument('--audit', action='store_true', help='Audit existing site items')
    parser.add_argument('--crawl', action='store_true', help='Crawl GitHub for new items')
    parser.add_argument('--full', action='store_true', help='Full maintenance: audit + crawl')
    parser.add_argument('--github-token', help='GitHub personal access token')
    parser.add_argument('--output', default='maintenance_report.json', help='Report output path')
    args = parser.parse_args()

    if not any([args.audit, args.crawl, args.full]):
        print("Usage: python3 maintenance.py --audit|--crawl|--full")
        sys.exit(1)

    audit_data = None
    crawl_data = None
    crawl_path = None

    if args.audit or args.full:
        audit_data = audit_site()

    if args.crawl or args.full:
        crawl_data, crawl_path = crawl_new(github_token=args.github_token)

    if audit_data or crawl_data:
        generate_report(audit_data, crawl_data, args.output)

    print("\n" + "="*70)
    print("MAINTENANCE COMPLETE")
    print("="*70)


if __name__ == '__main__':
    main()
