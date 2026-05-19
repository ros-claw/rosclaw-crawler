"""ROSClaw Ecology Crawler - Phase 3: GitHub Deep Search (PyGithub)"""

import time
from typing import List, Dict

from github import Auth, Github
from sqlalchemy.orm import Session

from config import GITHUB_TOKEN, GITHUB_SEARCH_QUERIES
from database import RosclawHubResource
from utils import (
    classify_embodied,
    normalize_github_url,
)


def build_github_client() -> Github:
    """Initialize authenticated GitHub client."""
    auth = Auth.Token(GITHUB_TOKEN)
    return Github(auth=auth, per_page=100, timeout=15)


MIN_STARS = 0  # keep even 0-star repos as long as they match topic heuristic


# Core keywords: must be about MCP / Agent Skill / Embodied AI / Physical AI
CORE_RELEVANCE_KEYWORDS = [
    "mcp", "model context protocol", "skill", "agent",
    "claude", "openclaw", "voltagent", "copilot", "cursor",
    "llm", "gpt", "chatbot", "assistant", "genai", "generative",
    "langchain", "llamaindex", "crewai", "autogen", "rag",
    "prompt", "chain", "tool use", "function calling",
    "robot", "robotics", "embodied", "physical ai", "physical",
    "ros", "isaac", "mujoco", "simulation", "sim-to-real",
    "slam", "vla", "manipulator", "drone", "iot", "hardware",
    "sensor", "kinematics", "dynamics", "control",
    "teleoperation", "dexterous", "bipedal", "quadruped",
    "spatial intelligence", "reinforcement learning", "imitation learning",
    "world model", "vision-language-action", "visual-language-action",
]

BLOCKLIST_KEYWORDS = [
    "coding interview", "interview university", "leetcode", "public api",
    "public-apis", "awesome list", "awesome-selfhosted", "awesome-go",
    "100 days", "python-100-days", "computer-science", "computer science",
    "selfhosted", "free programming books", "project-based-learning",
    "developer-roadmap", "system-design-primer", "build-your-own-x",
    "javascript-algorithms", "design-patterns-for-humans",
    "the-book-of-secret-knowledge", "every-programmer-should-know",
]


def is_repo_relevant(repo) -> bool:
    """
    Strict filter: must be about AI Agents, MCP, Skills, Robotics, or Physical AI.
    Star count is NOT a fallback — irrelevant popular repos are filtered out.
    """
    text = f"{repo.name} {repo.description or ''} {' '.join(repo.get_topics())}".lower()

    if any(kw in text for kw in BLOCKLIST_KEYWORDS):
        return False

    return any(kw in text for kw in CORE_RELEVANCE_KEYWORDS)


def infer_type_from_github(repo) -> str:
    """Decide type based on repo metadata and source context."""
    text = f"{repo.name} {repo.description or ''} {' '.join(repo.get_topics())}".lower()
    if "model context protocol" in text or "mcp" in repo.get_topics():
        return "mcp_server"
    if "skill" in repo.get_topics() or "agent-skill" in repo.get_topics():
        return "agent_skill"
    if " skill " in text or "agent skill" in text:
        return "agent_skill"
    if "mcp" in text and "skill" not in text:
        return "mcp_server"
    if "skill" in text and "mcp" not in text:
        return "agent_skill"
    # Broad heuristic fallback
    if "robot" in text or "ros" in text or "tool" in text:
        return "mcp_server"
    return "mcp_server"


def run_phase_3(
    session: Session,
    max_results_per_query: int = 100,
    sleep_between_queries: int = 12,
    sleep_between_repos: float = 1.5,
) -> int:
    """
    Phase 3 main runner.
    Uses PyGithub to search GitHub repos with Embodied AI / MCP / Skill queries.
    Adds polite delays and strict relevance filtering.
    Returns the number of new records inserted.
    """
    inserted_count = 0
    skipped_irrelevant = 0
    g = build_github_client()

    print("\n" + "=" * 60)
    print("PHASE 3: GitHub Deep Search (slow & curated mode)")
    print("=" * 60)

    for query in GITHUB_SEARCH_QUERIES:
        print(f"\n[QUERY] {query}")
        try:
            repos = g.search_repositories(query=query, sort="stars", order="desc")
            total = repos.totalCount
            print(f"[RESULTS] Total available: {total}")

            fetched = 0
            for repo in repos:
                if fetched >= max_results_per_query:
                    break

                # Relevance filter
                if not is_repo_relevant(repo):
                    skipped_irrelevant += 1
                    time.sleep(sleep_between_repos)
                    continue

                repo_url = normalize_github_url(repo.html_url)
                existing = (
                    session.query(RosclawHubResource)
                    .filter_by(repo_url=repo_url)
                    .first()
                )

                desc = repo.description or ""
                topics = [t for t in repo.get_topics()]
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
                    inserted_count += 1

                fetched += 1
                if fetched % 20 == 0:
                    print(f"  ... fetched {fetched}/{max_results_per_query} | skipped irrelevant {skipped_irrelevant}")
                time.sleep(sleep_between_repos)

            print(f"[DONE] Fetched {fetched} repos for query (skipped {skipped_irrelevant} irrelevant so far).")
            time.sleep(sleep_between_queries)

        except Exception as e:
            print(f"[ERROR] Query '{query}' failed: {e}")
            time.sleep(20)
            continue

    session.commit()
    print(f"\n[PHASE 3 COMPLETE] New records inserted: {inserted_count} | Total skipped irrelevant: {skipped_irrelevant}")
    return inserted_count


if __name__ == "__main__":
    from database import init_db, get_session

    engine = init_db("rosclaw_hub.db")
    db_session = get_session(engine)
    run_phase_3(db_session)
    db_session.close()
