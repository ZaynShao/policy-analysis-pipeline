from pathlib import Path
import json
from scripts.sync.run_sync import collect_policy_rows, collect_relation_rows, build_summary

def _write_bv(vault: Path, pid: str):
    d = vault / "_meta" / "business_view"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{pid}.yaml").write_text(
        f"pid: {pid}\nthemes: [power_market]\nprimary_theme: power_market\n"
        f"重要性: 4\nscores: {{D1: 5, D2: 4, D3: 4, D4: 4, D5: 4, D6: 5}}\n"
        f"value_tags: [机会]\n影响分析: {{加油: a, 充电: b, 电力_储能_V2G_交易: c}}\n"
        f"comprehensive: false\n", encoding="utf-8")

def test_collect_policy_rows(tmp_path):
    _write_bv(tmp_path, "P_2024_NDRC_718")
    rows = collect_policy_rows(tmp_path, pipeline_version=1)
    assert len(rows) == 1
    assert rows[0]["pipeline_pid"] == "P_2024_NDRC_718"
    assert rows[0]["importance"] == "MAJOR"

def test_collect_policy_rows_empty(tmp_path):
    assert collect_policy_rows(tmp_path, pipeline_version=1) == []

def test_collect_relation_rows(tmp_path):
    d = tmp_path / "1_extracted" / "relations"
    d.mkdir(parents=True, exist_ok=True)
    (d / "relations_canonical.jsonl").write_text(
        json.dumps({"from": "P_A", "to": "P_B", "rel": "derives_from",
                    "confidence": 0.9, "evidence": "ev1", "source": "s"}) + "\n",
        encoding="utf-8")
    rows = collect_relation_rows(tmp_path, pipeline_version=1)
    assert len(rows) == 1
    assert rows[0]["relation_type"] == "derives_from"
    assert rows[0]["from_pid"] == "P_A"
    assert rows[0]["to_pid"] == "P_B"
    assert rows[0]["evidence"] == "ev1"

def test_collect_relation_rows_skips_unknown_rel(tmp_path):
    d = tmp_path / "1_extracted" / "relations"
    d.mkdir(parents=True, exist_ok=True)
    (d / "relations_canonical.jsonl").write_text(
        json.dumps({"from": "P_A", "to": "P_B", "rel": "bogus",
                    "confidence": 0.9, "evidence": "ev1", "source": "s"}) + "\n",
        encoding="utf-8")
    rows = collect_relation_rows(tmp_path, pipeline_version=1)
    assert rows == []

def test_collect_relation_rows_skips_missing_required_fields(tmp_path):
    d = tmp_path / "1_extracted" / "relations"
    d.mkdir(parents=True, exist_ok=True)
    (d / "relations_canonical.jsonl").write_text(
        json.dumps({"to": "P_B", "rel": "references"}) + "\n",
        encoding="utf-8")
    rows = collect_relation_rows(tmp_path, pipeline_version=1)
    assert rows == []

def test_build_summary():
    s = build_summary(synced=10, skipped_override=2, relations=5, errors=["e1"])
    assert s["synced_count"] == 10
    assert s["skipped_override_count"] == 2
    assert s["relation_count"] == 5
    assert s["errors"] == ["e1"]
