#!/usr/bin/env python3
"""
ROSClaw Cleanup Report Generator

Generates a comprehensive audit report of all items on rosclaw.io
and produces deletion lists for manual or automated cleanup.
"""

import json
import urllib.request
from datetime import datetime
from strict_rosclaw_filter import strict_classify

BASE_URL = 'https://www.rosclaw.io'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.rosclaw.io/hub',
}


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


def audit(items: list, item_type: str) -> dict:
    """Audit items against strict criteria"""
    results = {'keep': [], 'remove': [], 'review': []}
    for item in items:
        name = item.get('name', '')
        desc = item.get('description', '')
        url = item.get('githubRepoUrl', '')
        decision, reason, confidence = strict_classify(name, desc, url)
        results[decision].append({
            'id': item.get('id'),
            'name': name,
            'displayName': item.get('displayName', ''),
            'description': desc,
            'url': url,
            'category': item.get('category', ''),
            'stars': item.get('githubStars', 0),
            'tags': item.get('tags', []),
            '_reason': reason,
            '_confidence': confidence,
        })
    return results


def generate_report(skills_audit: dict, mcps_audit: dict) -> str:
    """Generate markdown report"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    lines = [
        f"# ROSClaw Hub Cleanup Report\n",
        f"**Generated:** {timestamp}\n",
        "---\n",
    ]

    # Summary
    skills_total = sum(len(v) for v in skills_audit.values())
    mcps_total = sum(len(v) for v in mcps_audit.values())

    lines.extend([
        "## Summary\n",
        f"| Type | Total | Keep | Remove | Review |\n",
        f"|------|-------|------|--------|--------|\n",
        f"| Skills | {skills_total} | {len(skills_audit['keep'])} | {len(skills_audit['remove'])} | {len(skills_audit['review'])} |\n",
        f"| MCPs | {mcps_total} | {len(mcps_audit['keep'])} | {len(mcps_audit['remove'])} | {len(mcps_audit['review'])} |\n",
        f"| **Total** | **{skills_total + mcps_total}** | **{len(skills_audit['keep']) + len(mcps_audit['keep'])}** | **{len(skills_audit['remove']) + len(mcps_audit['remove'])}** | **{len(skills_audit['review']) + len(mcps_audit['review'])}** |\n",
        "\n---\n",
    ])

    # Skills to Remove
    lines.extend([
        "## Skills to REMOVE\n",
        f"Total: {len(skills_audit['remove'])}\n\n",
    ])
    for item in skills_audit['remove']:
        lines.append(f"- `{item['name']}` | {item['category']} | {item['stars']}⭐\n")
        lines.append(f"  - Reason: {item['_reason']}\n")
        lines.append(f"  - URL: {item['url']}\n")
        lines.append(f"  - ID: `{item['id']}`\n\n")

    # MCPs to Remove
    lines.extend([
        "## MCPs to REMOVE\n",
        f"Total: {len(mcps_audit['remove'])}\n\n",
    ])
    for item in mcps_audit['remove']:
        lines.append(f"- `{item['name']}` | {item['category']} | {item['stars']}⭐\n")
        lines.append(f"  - Reason: {item['_reason']}\n")
        lines.append(f"  - URL: {item['url']}\n")
        lines.append(f"  - ID: `{item['id']}`\n\n")

    # Items to Review
    lines.extend([
        "## Items to REVIEW\n",
        f"Total Skills: {len(skills_audit['review'])} | Total MCPs: {len(mcps_audit['review'])}\n\n",
    ])
    for item in skills_audit['review'] + mcps_audit['review']:
        lines.append(f"- `{item['name']}` | {item['category']} | {item['stars']}⭐\n")
        lines.append(f"  - Reason: {item['_reason']}\n")
        lines.append(f"  - URL: {item['url']}\n")
        lines.append(f"  - ID: `{item['id']}`\n\n")

    # Keep list
    lines.extend([
        "## Items to KEEP\n",
        f"Total Skills: {len(skills_audit['keep'])} | Total MCPs: {len(mcps_audit['keep'])}\n\n",
    ])
    for item in skills_audit['keep'] + mcps_audit['keep']:
        lines.append(f"- ✅ `{item['name']}` | {item['category']} | {item['stars']}⭐\n")
        lines.append(f"  - Reason: {item['_reason']}\n")
        lines.append(f"  - URL: {item['url']}\n\n")

    return ''.join(lines)


def main():
    print("=" * 80)
    print("ROSClaw Cleanup Report Generator")
    print("=" * 80)

    print("\n📡 Fetching skills...")
    skills = fetch_all('skills')
    print(f"   Got {len(skills)} skills")

    print("\n📡 Fetching MCPs...")
    mcps = fetch_all('mcp-packages')
    print(f"   Got {len(mcps)} mcps")

    print("\n🔍 Auditing...")
    skills_audit = audit(skills, 'skill')
    mcps_audit = audit(mcps, 'mcp')

    # Generate report
    report = generate_report(skills_audit, mcps_audit)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = f'/home/ubuntu/rosclaw/rosclaw_crawler/cleanup_report_{timestamp}.md'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n💾 Report saved: {report_file}")

    # Save JSON deletion list
    delete_list = {
        'timestamp': timestamp,
        'skills': [{'id': i['id'], 'name': i['name'], 'reason': i['_reason']} for i in skills_audit['remove']],
        'mcps': [{'id': i['id'], 'name': i['name'], 'reason': i['_reason']} for i in mcps_audit['remove']],
    }
    delete_file = f'/home/ubuntu/rosclaw/rosclaw_crawler/delete_list_{timestamp}.json'
    with open(delete_file, 'w', encoding='utf-8') as f:
        json.dump(delete_list, f, ensure_ascii=False, indent=2)
    print(f"💾 Delete list saved: {delete_file}")

    # Print summary
    print("\n" + "=" * 80)
    print("AUDIT SUMMARY")
    print("=" * 80)
    print(f"\nSKILLS: {len(skills)} total")
    print(f"  ✅ Keep:    {len(skills_audit['keep'])}")
    print(f"  ❌ Remove:  {len(skills_audit['remove'])}")
    print(f"  ⚠️  Review:  {len(skills_audit['review'])}")
    print(f"\nMCPS: {len(mcps)} total")
    print(f"  ✅ Keep:    {len(mcps_audit['keep'])}")
    print(f"  ❌ Remove:  {len(mcps_audit['remove'])}")
    print(f"  ⚠️  Review:  {len(mcps_audit['review'])}")
    print(f"\nTotal to remove: {len(skills_audit['remove']) + len(mcps_audit['remove'])}")
    print("=" * 80)


if __name__ == '__main__':
    main()
