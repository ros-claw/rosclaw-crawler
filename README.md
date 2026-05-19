# Rosclaw Crawler

An intelligent crawler for discovering, evaluating, and curating high-quality MCP servers and Agent Skills for embodied AI and robotics.

## Features

- **LLM-Powered Evaluation**: Uses DeepSeek API to intelligently judge repository relevance
- **Multi-Source Discovery**: Searches GitHub, awesome lists, and specialized directories
- **Strict Quality Control**: Embodied AI/robotics-focused with "宁可错杀" philosophy
- **Local Database**: SQLite-based tracking of all discovered and evaluated items
- **Batch Upload**: Automated upload to rosclaw.io with proper authentication
- **Audit Trail**: Complete history of all LLM judgments and decisions

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/ros-claw/rosclaw-crawler.git
cd rosclaw-crawler
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp .env.example .env
# Edit .env with your API keys
```

Required:
- `DEEPSEEK_API_KEY` - For LLM judgment
- `GITHUB_TOKEN` - For GitHub API access
- `ROSCALW_API_KEY` - For uploading to rosclaw.io

### 3. Run Crawler

```bash
# Quick crawl with LLM evaluation
python src/llm_quick_crawl.py "mcp-server robotics" "skill.md robot"

# Full batch crawl
python src/llm_batch_crawl.py

# Re-audit existing database
python src/llm_reaudit.py

# Upload approved items
python src/batch_upload.py
```

## Project Structure

```
rosclaw-crawler/
├── src/
│   ├── crawler_v2.py          # Rule-based crawler
│   ├── llm_judge.py           # LLM evaluation module
│   ├── llm_crawler_v2.py      # Full LLM crawler
│   ├── llm_quick_crawl.py     # Quick crawler
│   ├── llm_batch_crawl.py     # Batch processor
│   ├── llm_reaudit.py         # Re-audit tool
│   ├── batch_upload.py        # Upload to rosclaw.io
│   ├── database.py            # SQLite database
│   ├── site_cleanup.py        # Site cleanup tool
│   ├── maintenance.py         # Maintenance utilities
│   └── config_loader.py       # Configuration loader
├── data/                      # Local database (gitignored)
├── logs/                      # Log files (gitignored)
├── skills/                    # Curated skill definitions
├── .env.example               # Environment template
├── config.yaml                # Crawler configuration
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

## Quality Standards

Items must be:
1. **Genuine MCP Server or Agent Skill** form
2. **Directly relevant** to embodied intelligence/physical AI/robotics
3. **Callable by an AI agent** (not just algorithm/hardware)

Excluded:
- Pure algorithm repos without agent interface
- Pure hardware without MCP/skill integration
- Mass-generated template MCPs
- Generic IoT/camera tools without robotics context

## Database Schema

Two main tables:
- `skills` - Agent Skills with SKILL.md
- `mcps` - MCP Servers

Each tracked with:
- Source (github, site, llm_crawler)
- Decision (keep/remove)
- Confidence score
- LLM reasoning
- Site status (pending/uploaded)

## License

MIT License - See LICENSE file
