import json
from unittest.mock import patch

import pytest

from reporting import write_json_report


def test_failed_report_write_preserves_last_valid_report(tmp_path):
    report = tmp_path / "latest.json"
    write_json_report(report, {"status": "complete"})
    with patch("reporting.json.dump", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            write_json_report(report, {"status": "running"})
    assert json.loads(report.read_text()) == {"status": "complete"}
    assert list(tmp_path.iterdir()) == [report]
