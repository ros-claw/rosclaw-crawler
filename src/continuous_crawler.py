#!/usr/bin/env python3
"""
Continuous Crawler - Background process for ongoing discovery of robotics/embodied AI MCPs and Skills
Saves progress every 10 queries to avoid data loss
"""

import os
import sys
import json
import time
import sqlite3
from datetime import datetime

# Add src to path
sys.path.insert(0, '/home/ubuntu/rosclaw/rosclaw_crawler/src')

from crawler_unified import RosclawCrawler
from queries_embodied_ai import ALL_QUERIES

# Progress file
PROGRESS_FILE = '/tmp/continuous_crawl_progress.json'
STATE_FILE = '/tmp/continuous_crawl_state.json'

def load_state():
    """Load crawler state from file"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {'last_query_index': 0, 'total_found': 0, 'total_checked': 0}

def save_state(state):
    """Save crawler state to file"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def load_progress():
    """Load existing progress"""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_progress(results):
    """Save progress to file"""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

def main():
    print("="*70)
    print("CONTINUOUS CRAWLER - Background Process")
    print("="*70)
    print(f"Start time: {datetime.now().isoformat()}")
    
    # Initialize
    crawler = RosclawCrawler()
    state = load_state()
    all_results = load_progress()
    seen = set(r['name'] for r in all_results)
    
    print(f"Loaded {len(all_results)} existing items")
    print(f"Starting from query index: {state['last_query_index']}")
    print(f"Total queries: {len(ALL_QUERIES)}")
    
    # Process remaining queries
    for i in range(state['last_query_index'], len(ALL_QUERIES)):
        query = ALL_QUERIES[i]
        print(f"\n[{i+1}/{len(ALL_QUERIES)}] {query}")
        
        try:
            repos = crawler.search_github(query, 5)  # Check top 5 per query
            
            for repo in repos:
                name = repo['full_name']
                if name in seen:
                    continue
                seen.add(name)
                
                print(f"  Checking {name}...", end=" ", flush=True)
                
                try:
                    owner, repo_name = name.split('/', 1)
                    readme = crawler.fetch_readme(owner, repo_name)
                    judgment = crawler.llm_judge(name, repo.get('description', ''), readme)
                    
                    item = {
                        'name': name,
                        'stars': repo.get('stargazers_count', 0),
                        'description': repo.get('description', ''),
                        'url': repo.get('html_url', ''),
                        'llm': judgment,
                        'checked_at': datetime.now().isoformat(),
                    }
                    all_results.append(item)
                    
                    if judgment.get('relevant') and judgment.get('confidence', 0) >= 80:
                        print(f"OK ({judgment.get('confidence', 0)}%)")
                        # Add to database
                        item_type = 'skill' if 'skill' in name.lower() else 'mcp'
                        if crawler.add_to_db(item, item_type):
                            print(f"    -> Added to DB")
                    else:
                        print(f"NO ({judgment.get('confidence', 0)}%)")
                    
                    state['total_checked'] += 1
                    if judgment.get('relevant') and judgment.get('confidence', 0) >= 80:
                        state['total_found'] += 1
                    
                except Exception as e:
                    print(f"ERROR: {e}")
                
                # Rate limiting
                time.sleep(2)
            
            # Update state
            state['last_query_index'] = i + 1
            
            # Save progress every 5 queries
            if (i + 1) % 5 == 0:
                save_progress(all_results)
                save_state(state)
                print(f"\n  [SAVED] Progress: {len(all_results)} items, {state['total_found']} relevant")
            
        except Exception as e:
            print(f"\nQuery error: {e}")
            time.sleep(10)
            continue
    
    # Final save
    save_progress(all_results)
    save_state(state)
    
    print(f"\n{'='*70}")
    print("CRAWL COMPLETE")
    print(f"Total checked: {state['total_checked']}")
    print(f"Total relevant: {state['total_found']}")
    print(f"End time: {datetime.now().isoformat()}")
    print(f"{'='*70}")

if __name__ == '__main__':
    main()
