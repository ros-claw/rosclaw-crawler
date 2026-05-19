"""ROSClaw Ecology Crawler - 24/7 Continuous Mode

Slow, steady, bulletproof crawling.
Cycles through all data sources indefinitely.
Each new record is immediately analyzed and stored.
"""

import os
import sys
import time
import traceback
from datetime import datetime

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from github import Auth, Github, RateLimitExceededException
from sqlalchemy.orm import Session

from config import DB_PATH, GITHUB_SEARCH_QUERIES
from database import init_db, get_session
from phase1_awesome_lists import run_phase_1
from phase2_hub_directories import run_phase_2
from phase2b_mcpmarket import run_phase_2b
from phase3_github_search import (
    build_github_client,
    is_repo_relevant,
    infer_type_from_github,
)
from enhance_db import (
    run_enhancement_chunk,
    build_github_client as build_enhance_client,
)
from llm_analyzer import run_llm_analysis_chunk
from utils import classify_embodied, normalize_github_url
from database import RosclawHubResource

# --- GitHub Query Runner (one at a time, very polite) ---


def run_github_query(session: Session, g: Github, query: str, max_results: int = 100, sleep_repos: float = 2.0) -> int:
    """Run a single GitHub search query and insert results. Returns count inserted."""
    inserted = 0
    skipped = 0
    print(f"\n[GITHUB QUERY] {query}")

    try:
        repos = g.search_repositories(query=query, sort="stars", order="desc")
        total = repos.totalCount
        print(f"[RESULTS] Available: {total}")

        fetched = 0
        for repo in repos:
            if fetched >= max_results:
                break

            if not is_repo_relevant(repo):
                skipped += 1
                time.sleep(sleep_repos)
                continue

            repo_url = normalize_github_url(repo.html_url)
            existing = (
                session.query(RosclawHubResource)
                .filter_by(repo_url=repo_url)
                .first()
            )

            desc = repo.description or ""
            try:
                topics = [t for t in repo.get_topics()]
            except Exception:
                topics = []

            is_embodied, matched_tags = classify_embodied(
                f"{repo.name} {desc} {' '.join(topics)}"
            )
            resource_type = infer_type_from_github(repo)

            if existing:
                sources = set((existing.source or "").split(","))
                sources.add("github_search")
                existing.source = ",".join(s for s in sorted(sources) if s)
                existing.stars = repo.stargazers_count
                existing.description = desc
                if is_embodied:
                    existing.is_embodied = True
                    existing.domain_tags = list(
                        set((existing.domain_tags or []) + matched_tags)
                    )
                if existing.type != resource_type:
                    existing.type = resource_type
                session.merge(existing)
            else:
                record = RosclawHubResource(
                    type=resource_type,
                    source="github_search",
                    repo_url=repo_url,
                    name=repo.name,
                    description=desc,
                    domain_tags=matched_tags if matched_tags else [],
                    stars=repo.stargazers_count,
                    is_embodied=is_embodied,
                )
                session.add(record)
                inserted += 1

            fetched += 1
            if fetched % 20 == 0:
                session.commit()
                print(f"  ... fetched {fetched}/{max_results} | inserted={inserted} skipped={skipped}")
            time.sleep(sleep_repos)

        session.commit()
        print(f"[DONE] Query finished | inserted={inserted} skipped={skipped}")

    except RateLimitExceededException:
        print("[RATE LIMIT] Sleeping 60s before next query...")
        time.sleep(60)
    except Exception as e:
        print(f"[ERROR] Query failed: {e}")
        traceback.print_exc()
        time.sleep(30)

    return inserted


# --- Main 24/7 Loop ---


def main():
    print("=" * 70)
    print(" ROSCLAW 24/7 CONTINUOUS CRAWLER")
    print(" Slow & steady. Every record analyzed.")
    print("=" * 70)

    engine = init_db(DB_PATH)
    session = get_session(engine)
    g = build_enhance_client()
    query_idx = 0
    cycle = 0

    while True:
        cycle += 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{'='*70}")
        print(f" CYCLE #{cycle} | {now}")
        print(f"{'='*70}")

        # --- Phase 1: Awesome Lists (daily-ish, fast) ---
        try:
            run_phase_1(session)
        except Exception as e:
            print(f"[PHASE1 ERROR] {e}")
            traceback.print_exc()

        # Enhance chunk after phase 1
        run_enhancement_chunk(session, g, chunk_size=50)
        time.sleep(5)

        # --- Phase 2: Hub Directories ---
        try:
            run_phase_2(session)
        except Exception as e:
            print(f"[PHASE2 ERROR] {e}")
            traceback.print_exc()

        run_enhancement_chunk(session, g, chunk_size=50)
        time.sleep(5)

        # --- Phase 2B: MCP Market ---
        try:
            run_phase_2b(session)
        except Exception as e:
            print(f"[PHASE2B ERROR] {e}")
            traceback.print_exc()

        run_enhancement_chunk(session, g, chunk_size=50)
        time.sleep(5)

        # --- Phase 3: GitHub Deep Search (spread across cycle) ---
        print(f"\n[PHASE3] Running GitHub queries {query_idx+1}-{min(query_idx+10, len(GITHUB_SEARCH_QUERIES))} this cycle")
        for i in range(10):
            if query_idx >= len(GITHUB_SEARCH_QUERIES):
                query_idx = 0
                print("[PHASE3] All queries completed, restarting from top")

            q = GITHUB_SEARCH_QUERIES[query_idx]
            run_github_query(session, g, q, max_results=100, sleep_repos=2.0)
            query_idx += 1

            # After every github query, enhance a chunk of records
            p, e, c, f = run_enhancement_chunk(session, g, chunk_size=25)
            if p:
                print(f"  [POST-QUERY ENHANCE] processed={p} enhanced={e} corrected={c} filtered={f}")

            time.sleep(20)  # rest between queries

        # --- End-of-cycle mega enhancement ---
        print("\n[END CYCLE] Running mega enhancement chunks...")
        for _ in range(5):
            p, e, c, f = run_enhancement_chunk(session, g, chunk_size=50)
            if p == 0:
                break
            print(f"  processed={p} enhanced={e} corrected={c} filtered={f}")
            time.sleep(3)

        # --- LLM Deep Analysis (while crawler rests) ---
        print("\n[LLM PHASE] Running deep analysis batches...")
        for _ in range(3):
            proc, succ = run_llm_analysis_chunk(session, batch_size=3)
            if proc == 0:
                print("  no more repos to analyze")
                break
            print(f"  llm_processed={proc} llm_success={succ}")
            time.sleep(2)

        print(f"\n[SLEEP] Cycle {cycle} complete. Sleeping 30 minutes.")
        time.sleep(1800)


if __name__ == "__main__":
    main()
