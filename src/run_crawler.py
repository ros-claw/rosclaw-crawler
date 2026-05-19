"""ROSClaw Ecology Crawler - Main Orchestrator"""

import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DB_PATH
from database import init_db, get_session
from phase1_awesome_lists import run_phase_1
from phase2_hub_directories import run_phase_2
from phase2b_mcpmarket import run_phase_2b
from phase3_github_search import run_phase_3
from enhance_db import run_enhancement


def main():
    print("=" * 70)
    print(" ROSCLAW ECOLOGY CRAWLER")
    print(" Building the world's largest marketplace for Embodied AI & Physical AI")
    print("=" * 70)

    engine = init_db(DB_PATH)
    session = get_session(engine)

    total_inserted = 0
    try:
        # Phase 1: Awesome Lists
        total_inserted += run_phase_1(session)

        # Phase 2: Hub Directories (curl_cffi)
        total_inserted += run_phase_2(session)

        # Phase 2B: MCP Market deep scrape
        total_inserted += run_phase_2b(session)

        # Phase 3: GitHub Deep Search (slow, curated)
        total_inserted += run_phase_3(
            session,
            max_results_per_query=100,
            sleep_between_queries=15,
            sleep_between_repos=2.0,
        )

        # Enhancement: analyze every record in the DB
        print("\n" + "=" * 70)
        print("FINAL STEP: Deep analysis & enhancement of every record")
        print("=" * 70)
        run_enhancement(session)

    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Crawler stopped by user.")
    finally:
        session.close()

    print("\n" + "=" * 70)
    print(f" ALL PHASES COMPLETE | Total new records inserted: {total_inserted}")
    print(f" Database file: {os.path.abspath(DB_PATH)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
