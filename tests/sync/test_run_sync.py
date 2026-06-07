from pathlib import Path
import datetime
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

def _write_raw(vault: Path, pid: str, date: str = "2025-05-27", region: str = "全国"):
    d = vault / "0_raw" / "policies"
    d.mkdir(parents=True, exist_ok=True)
    if region == "dict":
        region_text = "region:\n  level: 省\n  code: '110000'\n  name: 北京市\n"
    else:
        region_text = f"region: {region}\n"
    (d / "anyname.md").write_text(
        f"---\nid: {pid}\ntitle: 核心标题\nissuer:\n  - 发文机关\n"
        f"date: {date}\nofficial_number: 文号\n"
        f"{region_text}provenance:\n  url: https://example.com\n---\n"
        f"## 政策原文\n正文\n",
        encoding="utf-8")

def test_collect_policy_rows(tmp_path):
    _write_raw(tmp_path, "P_FAKE_0001", region="dict")
    _write_bv(tmp_path, "P_FAKE_0001")
    rows, skipped = collect_policy_rows(tmp_path, pipeline_version=1)
    assert len(rows) == 1
    assert len(skipped) == 0
    assert rows[0]["title"] == "核心标题"
    assert rows[0]["source"] == "AUTO"
    assert rows[0]["issue_date"] == datetime.date(2025, 5, 27)
    assert rows[0]["region"] == "北京市"
    assert rows[0]["level"] == "省"
    assert rows[0]["pipeline_pid"] == "P_FAKE_0001"
    assert rows[0]["importance"] == "MAJOR"

def test_collect_policy_rows_skips_bad_date(tmp_path):
    _write_raw(tmp_path, "P_FAKE_0002", date="")
    _write_bv(tmp_path, "P_FAKE_0002")
    rows, skipped = collect_policy_rows(tmp_path, pipeline_version=1)
    assert rows == []
    assert skipped[0]["pid"] == "P_FAKE_0002"
    assert "reason" in skipped[0]

def test_collect_policy_rows_empty(tmp_path):
    assert collect_policy_rows(tmp_path, pipeline_version=1) == ([], [])

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
    assert s["skipped_invalid_count"] == 0
    s = build_summary(synced=10, skipped_override=2, relations=5,
                      errors=["e1"], skipped_invalid=3)
    assert s["skipped_invalid_count"] == 3
