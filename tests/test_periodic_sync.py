import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from database import init_db
from periodic_sync import run_stages


def test_failed_discovery_does_not_prevent_review_or_upload():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        db = root / "hub.db"
        init_db(db, quiet=True)
        stages = [(name, [name], root / f"{name}.json")
                  for name in ("sources", "review", "upload")]
        calls = []

        def runner(command, **kwargs):
            calls.append(command[0])
            return SimpleNamespace(returncode=1 if command[0] == "sources" else 0)

        assert run_stages(stages, root / "run.json", root / "latest.json", db, runner) == 1
        assert calls == ["sources", "review", "upload"]
        report = json.loads((root / "latest.json").read_text())
        assert report["status"] == "partial"
        assert report["stages"]["sources"]["status"] == "failed"
        assert report["stages"]["upload"]["status"] == "complete"
        assert json.loads((root / "run.json").read_text()) == report
