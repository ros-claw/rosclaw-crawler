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
- `ROSCLAW_API_KEY` - For uploading to rosclaw.io

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

## Source Synchronization

The maintained source list lives in `sources.yaml`. It separates high-trust
catalogs from broad discovery:

- NVIDIA `Physical AI` and `Robotics` groups are imported as individual skills
  and evaluated as individual skills.
- Every `SKILL.md` under the official Isaac Sim `skills/` directory is imported;
  relevance is decided per skill rather than trusting the repository as a whole.
- Official MCP Registry matches are staged with `decision=review`; registry
  presence proves publication, not ROSClaw relevance or operational safety.
- GitHub repository and `SKILL.md` code searches are staged for review and need
  `GITHUB_TOKEN` because GitHub code search does not support anonymous clients.

Run all sources against the local NVIDIA checkout:

```bash
python src/sync_sources.py
```

For unattended updates, use an isolated crawler-owned Git cache. This never
pulls into or modifies `nvidia_skills/skills`:

```bash
./run_periodic_sync.sh
```

Preview one source without changing the database:

```bash
python src/catalog_sync.py --source nvidia-skills --dry-run
python src/registry_sync.py --dry-run
```

Each catalog item has a stable `source_key`, source revision/path, version,
license and full-directory content hash. A changed uploaded item moves to
`pending_update`; an item removed upstream moves to lifecycle state `missing`
for review instead of being silently deleted.

Approved candidates are created or updated with:

```bash
python src/upload_to_site.py --dry-run
python src/upload_to_site.py
```

The uploader creates new entries with `POST` and refreshes existing entries via
the Hub item `PUT` endpoint. It preserves one Hub entry per skill directory, so
multi-skill repositories such as NVIDIA/skills are not collapsed into one card.

Example cron schedule for the complete automated pipeline:

```cron
17 3 * * * cd /path/to/rosclaw-crawler && ./run_periodic_sync.sh >> logs/source-sync.log 2>&1
```

Every non-dry run writes an audit report under `data/reports/` and uses a file
lock to prevent overlapping sync jobs.

For a persistent user service, install the units in `deploy/`, create
`~/.config/rosclaw-crawler/crawler.env` with mode `0600`, then enable the timer:

```bash
systemctl --user link "$PWD/deploy/rosclaw-crawler-sync.service"
systemctl --user link "$PWD/deploy/rosclaw-crawler-sync.timer"
systemctl --user enable --now rosclaw-crawler-sync.timer
systemctl --user start rosclaw-crawler-sync.service
```

Candidate review uses `physical_ai_taxonomy.yaml` to score format authenticity,
physical-domain anchors, operational usefulness, repository quality, duplicate
content and risk. Candidates that pass deterministic gates are then reviewed by
DeepSeek (with authenticated local Codex as a fallback) using a strict JSON contract and explicit relevance, authenticity,
usefulness, maintenance, confidence and risk thresholds. A model/API failure is
left queued for the next run; it can never publish a candidate. No manual
allowlist is required:

```bash
python src/candidate_reviewer.py --enrich-github --llm --apply
```

`run_periodic_sync.sh` and the systemd timer execute discovery, evidence
enrichment, AI review, decision application, Hub create/update/delete in that
order. The SQLite database records stable source identity, upstream revision,
directory content hashes, site state and the review model/prompt/input hash.
Unchanged candidates reuse the stored verdict and do not consume another model
call; changed candidates return to `decision=review` before a Hub update.

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
│   ├── catalog_sync.py        # Multi-skill catalog synchronization
│   ├── registry_sync.py       # Official MCP Registry discovery
│   ├── sync_sources.py        # Periodic source orchestrator
│   ├── database.py            # SQLite database
│   ├── site_cleanup.py        # Site cleanup tool
│   ├── maintenance.py         # Maintenance utilities
│   └── config_loader.py       # Configuration loader
├── data/                      # Local database (gitignored)
├── logs/                      # Log files (gitignored)
├── skills/                    # Curated skill definitions
├── .env.example               # Environment template
├── config.yaml                # Crawler configuration
├── sources.yaml               # Catalogs, registries and discovery queries
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
- LLM model, prompt version, input hash, scores, reasoning and risk evidence
- Site status (pending/uploaded)

## License

MIT License - See LICENSE file
