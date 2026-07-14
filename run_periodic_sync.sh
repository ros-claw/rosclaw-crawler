#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Fetch into data/source_cache so vendor checkouts and user changes are never modified.
python3 src/sync_sources.py --fetch-catalogs "$@"
# Revisit relevant repositories previously deferred for missing content. Items
# are only requeued for AI review when README/SKILL evidence actually changes.
python3 src/recheck_incomplete.py
review_status=0
python3 src/candidate_reviewer.py --enrich-github --llm --apply --fail-on-retry || review_status=$?
python3 src/upload_to_site.py
exit "$review_status"
