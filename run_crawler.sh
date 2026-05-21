#!/bin/bash
# Run continuous crawler with API keys

export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY}"
export GITHUB_TOKEN="${GITHUB_TOKEN}"
export ROSCLAW_API_KEY="${ROSCALW_API_KEY}"

cd /home/ubuntu/rosclaw/rosclaw_crawler
python3 src/continuous_crawler.py > /tmp/continuous_crawl.log 2>&1
