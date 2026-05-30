import json
from scripts.l1_audit.models import Finding
from scripts.l1_audit.report import write_outputs


def test_write_outputs_creates_report_and_jsonl(tmp_path):
    findings = [
        Finding(check="news_release", pid="P_X", detail={"label": "news_release"}, proposed_action="迁档"),
        Finding(check="dedup", pid="P_A", detail={"keep": "P_A", "dups": ["P_B"]}, proposed_action="去重"),
    ]
    out_dir = tmp_path / "state" / "source_ready"
    write_outputs(findings, total_policies=999, out_dir=str(out_dir))
    report = (out_dir / "audit_report.md").read_text(encoding="utf-8")
    assert "999" in report and "news_release: 1" in report and "dedup: 1" in report
    lines = (out_dir / "proposed_changes.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["pid"] == "P_X"
