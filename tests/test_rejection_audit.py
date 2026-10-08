import argparse
import json
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import pytest

from candidate_reviewer import CodexReviewer, LLMReviewError, load_taxonomy, review_item
from database import connect, insert_item
from rejection_audit import BatchCodexReviewer, audit, excerpt


def skill():
    return {
        "source": "test", "name": "robot-validation", "full_name": "test/robot-validation",
        "description": "Validate Isaac Sim robot simulation outputs.", "decision": "remove",
        "url": "https://github.com/test/robot-validation", "topics": [],
        "raw_data": {
            "metadata": {"name": "robot-validation", "description": "Validate Isaac Sim outputs."},
            "skill_content": "---\nname: robot-validation\ndescription: Validate Isaac Sim outputs.\n---\n"
            "## Workflow\nValidate robot assets and physics simulation deliverables.\n" * 8,
        },
    }


def verdict():
    return {
        "decision": "keep", "relevance_score": 95, "authenticity_score": 90,
        "operational_usefulness_score": 90, "maintenance_score": 50,
        "risk_score": 15, "confidence": .95, "categories": ["simulation-digital-twin"],
        "summary": "Validates robot simulation outputs.", "reasons": ["Valid format", "Concrete workflow"],
        "risks": [],
    }


def test_batch_requires_exact_identity_coverage():
    taxonomy = load_taxonomy()
    item = {**skill(), "id": 1, "topics": "[]"}
    baseline = review_item("skill", item, taxonomy)
    reviewer = BatchCodexReviewer()
    for outputs in ([], [dict(item_type="mcp", item_id=1, **verdict())],
                    [dict(item_type="skill", item_id=1, **verdict())] * 2):
        with patch.object(reviewer, "execute", return_value={"verdicts": outputs}):
            with pytest.raises(LLMReviewError):
                reviewer.review_batch([("skill", item, baseline)], taxonomy)


def test_excerpt_preserves_head_tail_and_marks_truncation():
    content = "FIRST" + "x" * 20000 + "LAST"
    shortened = excerpt(content, 1000)
    assert shortened.startswith("FIRST") and shortened.endswith("LAST")
    assert "CONTENT TRUNCATED" in shortened


def test_codex_process_disables_tools_and_does_not_receive_crawler_secrets(monkeypatch):
    for key in ("GITHUB_TOKEN", "ADMIN_API_KEY", "ROSCLAW_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.setenv(key, "test-secret")
    def execute(command, **kwargs):
        assert "test-secret" not in kwargs["env"].values()
        disabled = {command[i + 1] for i, value in enumerate(command) if value == "--disable"}
        assert {"shell_tool", "unified_exec", "apps", "plugins", "browser_use"} <= disabled
        assert 'web_search="disabled"' in command
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text('{"decision":"remove"}')
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    with patch("candidate_reviewer.subprocess.run", side_effect=execute):
        assert CodexReviewer().execute("classify", {})["decision"] == "remove"


def test_audit_preserves_history_and_reuses_semantic_checkpoint(tmp_path):
    db = tmp_path / "hub.db"
    insert_item("skill", skill(), db)
    args = argparse.Namespace(
        db=db, taxonomy=Path(__file__).resolve().parents[1] / "physical_ai_taxonomy.yaml",
        report=tmp_path / "report.json", workers=1, batch_size=4, timeout=10,
        enrich_github=False, apply=False,
    )
    def batch(self, candidates, taxonomy):
        return {(kind, item["id"]): verdict() for kind, item, _ in candidates}

    with patch.object(BatchCodexReviewer, "review_batch", autospec=True, side_effect=batch) as review:
        assert audit(args) == 0
        assert audit(args) == 0
        assert review.call_count == 1
    conn = connect(db)
    row = conn.execute("SELECT original_item,verdict FROM rejection_audits").fetchone()
    assert json.loads(row["original_item"])["decision"] == "remove"
    assert json.loads(row["verdict"])["decision"] == "keep"
    assert conn.execute("SELECT decision FROM skills").fetchone()[0] == "review"
    conn.close()


def test_failed_batch_is_not_approved_and_can_resume(tmp_path):
    db = tmp_path / "hub.db"
    insert_item("skill", skill(), db)
    args = argparse.Namespace(
        db=db, taxonomy=Path(__file__).resolve().parents[1] / "physical_ai_taxonomy.yaml",
        report=tmp_path / "report.json", workers=1, batch_size=4, timeout=10,
        enrich_github=False, apply=True,
    )
    with patch.object(BatchCodexReviewer, "review_batch", side_effect=LLMReviewError("temporary failure")):
        assert audit(args) == 1
    conn = connect(db)
    assert conn.execute("SELECT decision FROM skills").fetchone()[0] == "review"
    assert conn.execute("SELECT verdict FROM rejection_audits").fetchone()[0] is None
    conn.close()
    with patch.object(BatchCodexReviewer, "review_batch", return_value={("skill", 1): verdict()}):
        assert audit(args) == 0
    report = json.loads(args.report.read_text())
    assert report["audit_totals"]["skill"] == {"keep": 1, "remove": 0, "review": 0}


def test_changed_content_invalidates_checkpoint(tmp_path):
    db = tmp_path / "hub.db"
    insert_item("skill", skill(), db)
    args = argparse.Namespace(
        db=db, taxonomy=Path(__file__).resolve().parents[1] / "physical_ai_taxonomy.yaml",
        report=tmp_path / "report.json", workers=1, batch_size=4, timeout=10,
        enrich_github=False, apply=False,
    )
    with patch.object(BatchCodexReviewer, "review_batch", return_value={("skill", 1): verdict()}) as review:
        assert audit(args) == 0
        conn = connect(db)
        raw = json.loads(conn.execute("SELECT raw_data FROM skills").fetchone()[0])
        raw["skill_content"] += "\nValidate camera sensor output using a calibration scene."
        conn.execute("UPDATE skills SET raw_data=?", (json.dumps(raw),))
        conn.commit()
        conn.close()
        assert audit(args) == 0
        assert review.call_count == 2
