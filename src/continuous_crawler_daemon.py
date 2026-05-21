#!/usr/bin/env python3
"""
Continuous Crawler Daemon - Runs indefinitely in background
Cycles through all queries, sleeps, then repeats
Saves state and progress to survive restarts
"""

import os
import sys
import json
import time
import signal
import sqlite3
from datetime import datetime

sys.path.insert(0, '/home/ubuntu/rosclaw/rosclaw_crawler/src')

from crawler_unified import RosclawCrawler
from queries_embodied_ai import ALL_QUERIES

# State files
STATE_FILE = '/tmp/crawler_daemon_state.json'
PROGRESS_FILE = '/tmp/crawler_daemon_progress.json'
LOG_FILE = '/tmp/crawler_daemon.log'

# Graceful shutdown flag
running = True

def signal_handler(signum, frame):
    global running
    running = False
    log("Received shutdown signal, finishing current batch...")

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def log(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {
        'cycle': 0,
        'query_index': 0,
        'total_checked': 0,
        'total_found': 0,
        'last_run': None
    }

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_progress(progress):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)

def main():
    log("="*70)
    log("CONTINUOUS CRAWLER DAEMON STARTED")
    log("="*70)
    
    # Initialize
    crawler = RosclawCrawler()
    state = load_state()
    progress = load_progress()
    seen = set(p['name'] for p in progress)
    
    log(f"Loaded {len(progress)} existing items")
    log(f"Starting from cycle {state['cycle']}, query {state['query_index']}")
    
    while running:
        cycle = state['cycle']
        log(f"\n{'='*70}")
        log(f"CYCLE {cycle} STARTED")
        log(f"{'='*70}")
        
        # Process all queries in this cycle
        for i in range(state['query_index'], len(ALL_QUERIES)):
            if not running:
                break
                
            query = ALL_QUERIES[i]
            log(f"[{i+1}/{len(ALL_QUERIES)}] {query}")
            
            try:
                repos = crawler.search_github(query, 5)
                log(f"  Found {len(repos)} repos")
                
                for repo in repos:
                    if not running:
                        break
                        
                    name = repo['full_name']
                    if name in seen:
                        continue
                    seen.add(name)
                    
                    try:
                        owner, repo_name = name.split('/', 1)
                        readme = crawler.fetch_readme(owner, repo_name)
                        judgment = crawler.llm_judge(
                            name, 
                            repo.get('description', ''), 
                            readme
                        )
                        
                        item = {
                            'name': name,
                            'stars': repo.get('stargazers_count', 0),
                            'description': repo.get('description', ''),
                            'url': repo.get('html_url', ''),
                            'llm': judgment,
                            'checked_at': datetime.now().isoformat(),
                            'cycle': cycle
                        }
                        progress.append(item)
                        
                        if judgment.get('relevant') and judgment.get('confidence', 0) >= 80:
                            log(f"  ✅ {name} ({judgment.get('confidence', 0)}%)")
                            item_type = 'skill' if 'skill' in name.lower() else 'mcp'
                            if crawler.add_to_db(item, item_type):
                                log(f"    -> Added to DB")
                            state['total_found'] += 1
                        else:
                            log(f"  ❌ {name} ({judgment.get('confidence', 0)}%)")
                        
                        state['total_checked'] += 1
                        
                    except Exception as e:
                        log(f"  ERROR checking {name}: {e}")
                    
                    time.sleep(2)  # Rate limiting
                
                # Save progress every 5 queries
                if (i + 1) % 5 == 0:
                    save_progress(progress)
                    state['query_index'] = i + 1
                    save_state(state)
                    log(f"  [SAVED] {len(progress)} total items, {state['total_found']} relevant")
                
            except Exception as e:
                log(f"Query error: {e}")
                time.sleep(10)
                continue
        
        # Cycle complete
        state['cycle'] += 1
        state['query_index'] = 0
        state['last_run'] = datetime.now().isoformat()
        save_state(state)
        save_progress(progress)
        
        log(f"\n{'='*70}")
        log(f"CYCLE {cycle} COMPLETE")
        log(f"Total checked this cycle: {state['total_checked']}")
        log(f"Total relevant: {state['total_found']}")
        log(f"{'='*70}")
        
        if running:
            log("Sleeping for 1 hour before next cycle...")
            for _ in range(3600):  # 1 hour
                if not running:
                    break
                time.sleep(1)
    
    # Shutdown
    log("\nShutting down gracefully...")
    save_state(state)
    save_progress(progress)
    log(f"Final state: {state}")
    log("Goodbye!")

if __name__ == '__main__':
    main()
