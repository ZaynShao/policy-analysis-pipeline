import json
from scripts.l1_audit.models import Finding
from scripts.l1_audit.report import write_outputs

def _findings():
    return [
        Finding(check="news_release", pid="P_X", detail={"label": "news_release", "confidence": 0.9}, proposed_action="迁档"),
        Finding(check="id_issuer", pid="P_C1", detail={"source": "canonical", "id_short": "CCGO", "expected_short": "GO"}, proposed_action="重算"),
        Finding(check="id_issuer", pid="P_K1", detail={"source": "keyword", "id_short": "GO", "issuer": ["银川市发展和改革委员会"]}, proposed_action="复核"),
        Finding(check="dedup", pid="P_A", detail={"keep": "P_A", "dups": ["P_B"]}, proposed_action="去重"),
        Finding(check="p1900", pid="P_1900_SX_x", detail={}, proposed_action="backlog"),
    ]

def test_counts_and_total(tmp_path):
    out = tmp_path / "state" / "source_ready"
    write_outputs(_findings(), total_policies=999, out_dir=str(out))
    r = (out / "audit_report.md").read_text(encoding="utf-8")
    assert "999" in r
    assert "news_release: 1" in r and "id_issuer: 2" in r and "dedup: 1" in r

def test_id_issuer_layered_section(tmp_path):
    out = tmp_path / "state" / "source_ready"
    write_outputs(_findings(), total_policies=999, out_dir=str(out))
    r = (out / "audit_report.md").read_text(encoding="utf-8")
    assert "id_issuer 分层" in r
    assert "高置信" in r and "低置信" in r
    assert "GO" in r                      # top id_short 出现
    assert "P_C1" in r                    # 高置信明细列出该 pid

def test_dedup_and_news_sections(tmp_path):
    out = tmp_path / "state" / "source_ready"
    write_outputs(_findings(), total_policies=999, out_dir=str(out))
    r = (out / "audit_report.md").read_text(encoding="utf-8")
    assert "P_A" in r and "P_B" in r      # dedup 组明细
    assert "P_X" in r                     # news 候选列出

def test_jsonl_unchanged(tmp_path):
    out = tmp_path / "state" / "source_ready"
    write_outputs(_findings(), total_policies=999, out_dir=str(out))
    lines = (out / "proposed_changes.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 5
    assert json.loads(lines[0])["pid"] == "P_X"
