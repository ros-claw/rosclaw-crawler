"""ROSClaw Ecology Crawler - Continuous Database Enhancement & Filtering

Resumable, bulletproof per-record analyzer.
Processes records in chunks, saves progress, handles errors per-record.
"""

import os
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from github import (
    Auth,
    Github,
    RateLimitExceededException,
    UnknownObjectException,
    BadCredentialsException,
    GithubException,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import GITHUB_TOKEN
from database import RosclawHubResource, init_db, get_session
from utils import classify_embodied, normalize_github_url

# Force unbuffered stdout so logs appear immediately
sys.stdout.reconfigure(line_buffering=True)

PROGRESS_FILE = ".enhance_progress"
CHUNK_SIZE = 50
MAX_RETRIES_PER_REPO = 3


def build_github_client() -> Github:
    auth = Auth.Token(GITHUB_TOKEN)
    return Github(auth=auth, per_page=100, timeout=15)


# STRICT relevance: must be about MCP / Agent Skills / Embodied AI / Physical AI
STRICT_CORE_KEYWORDS = [
    # MCP / Agent / Skill
    "mcp", "model context protocol", "skill", "agent",
    "claude", "openclaw", "voltagent", "copilot", "cursor",
    "llm", "gpt", "chatbot", "assistant", "genai", "generative",
    "langchain", "llamaindex", "crewai", "autogen", "rag",
    "prompt", "chain", "tool use", "function calling",
    # Embodied / Robotics / Physical AI
    "robot", "robotics", "embodied", "physical ai", "physical",
    "ros", "isaac", "mujoco", "simulation", "sim-to-real",
    "slam", "vla", "manipulator", "drone", "iot", "hardware",
    "sensor", "kinematics", "dynamics", "control",
    "teleoperation", "dexterous", "bipedal", "quadruped",
    "spatial intelligence", "reinforcement learning", "imitation learning",
    "world model", "vision-language-action", "visual-language-action",
]

# Blocklist: definitely unrelated generic repos that slipped through
BLOCKLIST_KEYWORDS = [
    "coding interview", "interview university", "leetcode", "public api",
    "public-apis", "awesome list", "awesome-selfhosted", "awesome-go",
    "100 days", "python-100-days", "computer-science", "computer science",
    "selfhosted", "free programming books", "project-based-learning",
    "developer-roadmap", "system-design-primer", "build-your-own-x",
    "javascript-algorithms", "tensorflow-internals", "design-patterns-for-humans",
    "the-book-of-secret-knowledge", "every-programmer-should-know",
]


def is_relevant(name: Optional[str], description: Optional[str], topics: List[str], stars: int) -> bool:
    full_text = f"{name or ''} {description or ''} {' '.join(topics)}".lower()

    # Hard blocklist first
    if any(kw.lower() in full_text for kw in BLOCKLIST_KEYWORDS):
        return False

    # Must match at least one strict core keyword
    matched = any(kw.lower() in full_text for kw in STRICT_CORE_KEYWORDS)
    return matched


def infer_type_from_content(name: str, description: Optional[str], topics: List[str], source: str) -> str:
    text = f"{name} {description or ''} {' '.join(topics)}".lower()

    skill_sources = ["awesome-claude-skills", "awesome-openclaw-skills", "awesome-agent-skills"]
    if any(ss in source.lower() for ss in skill_sources):
        return "agent_skill"
    if any(ss in source.lower() for ss in ["mcpmarket.com/tools/skills", "/tools/skills/"]):
        return "agent_skill"

    if "model context protocol" in text or "mcp" in topics or "mcp-server" in topics:
        return "mcp_server"
    if "skill" in topics or "agent-skill" in topics:
        return "agent_skill"
    if " skill " in text or "agent skill" in text or "skills for" in text:
        return "agent_skill"
    if " claude skill" in text or "openclaw skill" in text or "cursor skill" in text:
        return "agent_skill"

    if "mcp" in text and "skill" not in text:
        return "mcp_server"
    if "skill" in text and "mcp" not in text:
        return "agent_skill"

    if "robot" in text or "ros" in text or ("tool" in text and "plugin" in text):
        return "mcp_server"
    return "mcp_server"


def get_progress() -> int:
    if not os.path.exists(PROGRESS_FILE):
        return 0
    try:
        with open(PROGRESS_FILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return 0


def save_progress(last_id: int) -> None:
    with open(PROGRESS_FILE, "w") as f:
        f.write(str(last_id))


def run_enhancement_chunk(session: Session, g: Github, chunk_size: int = CHUNK_SIZE) -> Tuple[int, int, int, int]:
    """
    Process the next chunk of un-enhanced records.
    Returns: (processed, enhanced_api, type_corrected, filtered)
    """
    last_id = get_progress()

    records = (
        session.query(RosclawHubResource)
        .filter(RosclawHubResource.id > last_id)
        .order_by(RosclawHubResource.id)
        .limit(chunk_size)
        .all()
    )

    if not records:
        # Reset progress to start from beginning for continuous re-validation
        save_progress(0)
        records = (
            session.query(RosclawHubResource)
            .order_by(RosclawHubResource.id)
            .limit(chunk_size)
            .all()
        )
        print(f"[ENHANCE] Reset progress, re-validating from top (cycle mode)")

    processed = enhanced_api = type_corrected = filtered = 0
    max_id = last_id

    for rec in records:
        processed += 1
        max_id = rec.id

        try:
            norm_url = normalize_github_url(rec.repo_url)
            if not norm_url:
                # Non-repo GitHub path (e.g. user-attachments, features)
                rec.is_relevant = False
                filtered += 1
                continue
            parts = norm_url.replace("https://github.com/", "").split("/", 1)
            owner, repo_name = parts[0], parts[1] if len(parts) > 1 else ""
            if not owner or not repo_name:
                rec.is_relevant = False
                filtered += 1
                continue

            needs_api = (
                (rec.stars is None or rec.stars == 0)
                or (not rec.description or len(rec.description) < 10)
                or (rec.name == repo_name and len(repo_name) < 3)
            )

            description = rec.description or ""
            stars = rec.stars or 0
            topics: List[str] = []

            if needs_api:
                api_success = False
                for attempt in range(1, MAX_RETRIES_PER_REPO + 1):
                    try:
                        repo = g.get_repo(f"{owner}/{repo_name}")
                        description = repo.description or description
                        stars = repo.stargazers_count
                        topics = [t for t in repo.get_topics()]
                        rec.description = description
                        rec.stars = stars
                        enhanced_api += 1
                        api_success = True
                        break
                    except UnknownObjectException:
                        # Repo deleted or private - mark irrelevant unless already popular
                        if stars < 5:
                            rec.is_relevant = False
                            filtered += 1
                        api_success = True  # we got a definitive answer
                        break
                    except RateLimitExceededException:
                        print(f"[RATE LIMIT] id={rec.id} attempt={attempt}. Sleeping 120s...")
                        time.sleep(120)
                        # re-create client in case token/session state degraded
                        g = build_github_client()
                        continue
                    except BadCredentialsException as bce:
                        print(f"[401 BAD CREDENTIALS] id={rec.id} attempt={attempt}: {bce}. Sleeping 300s...")
                        time.sleep(300)
                        g = build_github_client()
                        continue
                    except GithubException as ge:
                        if ge.status == 401:
                            print(f"[401 UNAUTHORIZED] id={rec.id} attempt={attempt}: {ge}. Sleeping 300s...")
                            time.sleep(300)
                            g = build_github_client()
                            continue
                        elif ge.status == 403:
                            print(f"[403 FORBIDDEN] id={rec.id} attempt={attempt}: {ge}. Sleeping 120s...")
                            time.sleep(120)
                            g = build_github_client()
                            continue
                        elif ge.status == 404:
                            # Treat as deleted
                            if stars < 5:
                                rec.is_relevant = False
                                filtered += 1
                            api_success = True
                            break
                        elif ge.status >= 500:
                            print(f"[GITHUB SERVER ERROR {ge.status}] id={rec.id} attempt={attempt}. Sleeping 30s...")
                            time.sleep(30)
                            continue
                        else:
                            print(f"[GITHUB ERROR {ge.status}] id={rec.id} attempt={attempt}: {ge}. Skipping.")
                            break
                    except Exception as e:
                        print(f"[WARN] id={rec.id} attempt={attempt} unexpected error: {e}")
                        break

                if not api_success:
                    # Could not reach API for this repo; skip to next record so we don't deadlock
                    print(f"[SKIP API] id={rec.id} {owner}/{repo_name} after {MAX_RETRIES_PER_REPO} attempts")
                    continue

                time.sleep(1.0)  # inter-record politeness

            # Relevance
            relevant = is_relevant(rec.name, description, topics, stars)
            if not relevant:
                rec.is_relevant = False
                filtered += 1
            else:
                rec.is_relevant = True

            # Type correction
            new_type = infer_type_from_content(
                rec.name or repo_name, description, topics, rec.source
            )
            if new_type != rec.type:
                rec.type = new_type
                type_corrected += 1

            # Embodied tags
            is_embodied, matched_tags = classify_embodied(
                f"{rec.name or ''} {description} {' '.join(topics)}"
            )
            rec.is_embodied = is_embodied
            if matched_tags:
                existing_tags = set(rec.domain_tags or [])
                existing_tags.update(matched_tags)
                rec.domain_tags = sorted(list(existing_tags))

            try:
                session.merge(rec)
                session.flush()
            except Exception as e:
                print(f"[WARN FLUSH] id={rec.id}: {e}")
                try:
                    session.rollback()
                except Exception:
                    pass
                # Try once more after rollback
                try:
                    session.merge(rec)
                    session.flush()
                except Exception as e2:
                    print(f"[SKIP] id={rec.id} after rollback: {e2}")
                    try:
                        session.rollback()
                    except Exception:
                        pass
                    continue
        except Exception as e:
            print(f"[ERROR] id={rec.id}: {e}")
            traceback.print_exc()
            try:
                session.rollback()
            except Exception:
                pass
            continue

    try:
        session.commit()
        save_progress(max_id)
    except Exception as e:
        print(f"[CHUNK COMMIT ERROR] {e}")
        try:
            session.rollback()
        except Exception:
            pass
    return processed, enhanced_api, type_corrected, filtered


def run_enhancement_continuous(session: Session, total_cycles: int = 0) -> None:
    """
    Run enhancement continuously in chunks.
    total_cycles=0 means infinite loop.
    """
    g = build_github_client()
    cycle = 0

    print("=" * 60)
    print("CONTINUOUS DB ENHANCEMENT MODE")
    print("Processing every record carefully, one by one")
    print("=" * 60)

    while True:
        if total_cycles > 0 and cycle >= total_cycles:
            break
        cycle += 1

        try:
            processed, enhanced, corrected, filtered = run_enhancement_chunk(session, g, CHUNK_SIZE)
            print(
                f"[CHUNK {cycle}] processed={processed} enhanced={enhanced} "
                f"corrected={corrected} filtered={filtered}"
            )
        except Exception as e:
            print(f"[CHUNK FATAL] {e}")
            traceback.print_exc()
            try:
                session.rollback()
            except Exception:
                pass
            time.sleep(10)
            continue

        if processed == 0:
            print("[SLEEP] No records to process, sleeping 300s")
            time.sleep(300)
        else:
            time.sleep(2)  # tiny breath between chunks


if __name__ == "__main__":
    engine = init_db("rosclaw_hub.db")
    db_session = get_session(engine)
    try:
        run_enhancement_continuous(db_session)
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Enhancer stopped by user.")
    finally:
        db_session.close()
