#!/bin/bash
# Continuous crawler for rosclaw
# Runs every 6 hours to find new high-quality MCPs and Skills

set -e

LOG_DIR="/home/ubuntu/rosclaw/rosclaw_crawler/logs"
DATA_DIR="/home/ubuntu/rosclaw/rosclaw_crawler/data"
mkdir -p "$LOG_DIR"

GITHUB_TOKEN="GITHUB_TOKEN_PLACEHOLDER"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/crawl_$TIMESTAMP.log"

echo "========================================" | tee -a "$LOG_FILE"
echo "Rosclaw Continuous Crawler - $TIMESTAMP" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

cd /home/ubuntu/rosclaw/rosclaw_crawler

# Step 1: Audit current site state
echo "[1/3] Auditing current site state..." | tee -a "$LOG_FILE"
python3 -c "
import sys
sys.path.insert(0, 'src')
from sync_to_db import sync_site_items
from database import update_site_state, get_stats
import json

skill_count = sync_site_items('skill')
mcp_count = sync_site_items('mcp')
stats = get_stats()
quality = (stats['skills']['keep'] + stats['mcps']['keep']) / max(stats['skills']['total'] + stats['mcps']['total'], 1) * 100
update_site_state(stats['skills']['total'], stats['mcps']['total'], quality)
print(f'Audit complete: {skill_count} skills, {mcp_count} mcps')
print(f'Quality score: {quality:.1f}%')
" 2>&1 | tee -a "$LOG_FILE"

# Step 2: Crawl GitHub for new items
echo "[2/3] Crawling GitHub for new items..." | tee -a "$LOG_FILE"
OUTPUT_FILE="crawler_v2_results_$TIMESTAMP.json"
python3 src/crawler_v2.py \
    --github-token "$GITHUB_TOKEN" \
    --max-per-query 10 \
    --output "$OUTPUT_FILE" 2>&1 | tee -a "$LOG_FILE"

# Step 3: Sync crawl results to DB
echo "[3/3] Syncing results to database..." | tee -a "$LOG_FILE"
python3 -c "
import sys
sys.path.insert(0, 'src')
from sync_to_db import sync_crawl_results
from database import get_stats
import json

count = sync_crawl_results('$OUTPUT_FILE', 'mcp')
stats = get_stats()
print(f'Synced {count} items')
print(f'DB stats: {json.dumps(stats, indent=2)}')
" 2>&1 | tee -a "$LOG_FILE"

echo "========================================" | tee -a "$LOG_FILE"
echo "Crawl complete at $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# Keep only last 30 log files
ls -t "$LOG_DIR"/crawl_*.log | tail -n +31 | xargs -r rm
