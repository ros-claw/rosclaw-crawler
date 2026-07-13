#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Fetch into data/source_cache so vendor checkouts and user changes are never modified.
python3 src/sync_sources.py --fetch-catalogs "$@"
python3 src/candidate_reviewer.py --enrich-github --llm --apply
python3 src/upload_to_site.py
