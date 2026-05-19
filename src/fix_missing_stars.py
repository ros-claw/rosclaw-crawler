#!/usr/bin/env python3
"""ROSClaw - Targeted repair for missing stars/description. No more endless looping."""
import os
import sys
import time
import traceback
from datetime import datetime, timezone

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from github import Auth, Github, RateLimitExceededException, UnknownObjectException, BadCredentialsException, GithubException
from sqlalchemy.orm import Session
from sqlalchemy import or_

from config import GITHUB_TOKEN
from database import RosclawHubResource, init_db, get_session
from utils import classify_embodied, normalize_github_url
from enhance_db import is_relevant, infer_type_from_content, build_github_client, MAX_RETRIES_PER_REPO

CHUNK_SIZE = 25

def run_targeted_chunk(session: Session, g: Github) -> tuple:
    records = (
        session.query(RosclawHubResource)
        .filter(
            or_(
                RosclawHubResource.stars == None,
                RosclawHubResource.stars == 0,
                RosclawHubResource.description == None,
                RosclawHubResource.description == ""
            )
        )
        .order_by(RosclawHubResource.id)
        .limit(CHUNK_SIZE)
        .all()
    )

    if not records:
        return 0, 0, 0, 0

    processed = enhanced_api = type_corrected = filtered = 0

    for rec in records:
        processed += 1
        try:
            norm_url = normalize_github_url(rec.repo_url)
            if not norm_url:
                rec.is_relevant = False
                filtered += 1
                continue
            parts = norm_url.replace("https://github.com/", "").split("/", 1)
            owner, repo_name = parts[0], parts[1] if len(parts) > 1 else ""
            if not owner or not repo_name:
                rec.is_relevant = False
                filtered += 1
                continue

            api_success = False
            description = rec.description or ""
            stars = rec.stars or 0
            topics = []

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
                    if stars < 5:
                        rec.is_relevant = False
                        filtered += 1
                    api_success = True
                    break
                except RateLimitExceededException:
                    print(f"[RATE LIMIT] id={rec.id} attempt={attempt}. Sleeping 120s...")
                    time.sleep(120)
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
                print(f"[SKIP API] id={rec.id} {owner}/{repo_name} after {MAX_RETRIES_PER_REPO} attempts")
                continue

            time.sleep(0.8)

            relevant = is_relevant(rec.name, description, topics, stars)
            if not relevant:
                rec.is_relevant = False
                filtered += 1
            else:
                rec.is_relevant = True

            new_type = infer_type_from_content(rec.name or repo_name, description, topics, rec.source)
            if new_type != rec.type:
                rec.type = new_type
                type_corrected += 1

            is_embodied, matched_tags = classify_embodied(f"{rec.name or ''} {description} {' '.join(topics)}")
            rec.is_embodied = is_embodied
            if matched_tags:
                existing_tags = set(rec.domain_tags or [])
                existing_tags.update(matched_tags)
                rec.domain_tags = sorted(list(existing_tags))

            session.merge(rec)
            session.flush()
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
    except Exception as e:
        print(f"[CHUNK COMMIT ERROR] {e}")
        try:
            session.rollback()
        except Exception:
            pass
    return processed, enhanced_api, type_corrected, filtered


def main():
    try:
        db_path = os.path.abspath("rosclaw_hub.db")
        print(f"[DEBUG] cwd={os.getcwd()} db_path={db_path}")
        engine = init_db(db_path)
        session = get_session(engine)
        g = build_github_client()
        chunk = 0
        print("=" * 60)
        print("TARGETED MISSING STARS/DESCRIPTION REPAIR")
        print("Processing only records that need API calls")
        print("=" * 60)

        # Debug: show initial count
        initial = session.query(RosclawHubResource).filter(
            or_(
                RosclawHubResource.stars == None,
                RosclawHubResource.stars == 0,
                RosclawHubResource.description == None,
                RosclawHubResource.description == ""
            )
        ).count()
        print(f"[INIT] Records needing repair: {initial}")

        while True:
            chunk += 1
            p, e, c, f = run_targeted_chunk(session, g)
            print(f"[CHUNK {chunk}] processed={p} enhanced={e} corrected={c} filtered={f}  {datetime.now().strftime('%H:%M:%S')}")
            if p == 0:
                print("[DONE] No more missing stars/descriptions!")
                break
            time.sleep(1)
    except Exception as e:
        print(f"[FATAL] {e}")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
