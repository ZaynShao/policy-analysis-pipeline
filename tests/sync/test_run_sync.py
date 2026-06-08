from pathlib import Path
import datetime
import json
import sys
import types
from scripts.sync.run_sync import collect_policy_rows, collect_relation_rows, build_summary
from scripts.sync import run_sync as run_sync_mod

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

def test_collect_commentary_rows(tmp_path):
    import json
    from scripts.sync import run_sync as m
    d = tmp_path / "1_extracted"
    d.mkdir(parents=True)
    lines = [
        {"commentary_id": "C_1", "title": "T1", "evidence": "E1",
         "related_policy_ids": ["P_in", "P_missing"], "theme_ids": ["power_market"],
         "signal_role": "risk", "confidence": 0.7, "source_account": "中电联",
         "business_tag": "power", "path": "0_raw/commentaries/x.md"},
        {"title": "无id跳过", "related_policy_ids": []},  # 无 commentary_id → 跳过
    ]
    (d / "commentary_signals.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in lines), encoding="utf-8")
    rows = m.collect_commentary_rows(tmp_path, 1)
    assert len(rows) == 1
    r = rows[0]
    assert r["commentary_id"] == "C_1"
    assert json.loads(r["related_policy_pids"]) == ["P_in", "P_missing"]  # 悬挂原样
    assert json.loads(r["theme_ids"]) == ["power_market"]
    assert r["business_tag"] == "power"
    assert r["pipeline_version"] == 1

def test_collect_commentary_rows_absent_file(tmp_path):
    from scripts.sync import run_sync as m
    assert m.collect_commentary_rows(tmp_path, 1) == []  # 文件不存在→空

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


class FakeRunConn:
    def __init__(self):
        self.commits = 0
        self.closed = False

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


def test_run_writes_notification_when_errors(tmp_path, monkeypatch):
    conn = FakeRunConn()
    executed = []
    monkeypatch.setitem(sys.modules, "psycopg2", types.SimpleNamespace(connect=lambda _: conn))
    monkeypatch.setattr(run_sync_mod, "collect_policy_rows",
                        lambda vault, version: ([{"pipeline_pid": "P_A"}], []))
    monkeypatch.setattr(run_sync_mod, "collect_relation_rows", lambda vault, version: [])
    monkeypatch.setattr(run_sync_mod.pg_writer, "build_policy_upsert",
                        lambda row: ("INSERT Policy", {"pid": row["pipeline_pid"]}))
    monkeypatch.setattr(run_sync_mod.pg_writer, "build_notification_insert",
                        lambda **kw: ("INSERT INTO \"Notification\"", kw))

    def fake_execute(conn_arg, sql, params):
        executed.append(sql)
        if sql == "INSERT Policy":
            raise RuntimeError("policy failed")

    monkeypatch.setattr(run_sync_mod.pg_writer, "execute_with_savepoint", fake_execute)

    summary = run_sync_mod.run(tmp_path, tmp_path / "state", 1, "postgres://fake")

    assert any('"Notification"' in sql for sql in executed)
    assert summary["errors"] == ["policy P_A: policy failed"]
    assert conn.commits == 2
    assert conn.closed is True


def test_run_records_notification_write_failure(tmp_path, monkeypatch):
    conn = FakeRunConn()
    monkeypatch.setitem(sys.modules, "psycopg2", types.SimpleNamespace(connect=lambda _: conn))
    monkeypatch.setattr(run_sync_mod, "collect_policy_rows",
                        lambda vault, version: ([{"pipeline_pid": "P_A"}], []))
    monkeypatch.setattr(run_sync_mod, "collect_relation_rows", lambda vault, version: [])
    monkeypatch.setattr(run_sync_mod.pg_writer, "build_policy_upsert",
                        lambda row: ("INSERT Policy", {"pid": row["pipeline_pid"]}))
    monkeypatch.setattr(run_sync_mod.pg_writer, "build_notification_insert",
                        lambda **kw: ("INSERT INTO \"Notification\"", kw))

    def fake_execute(conn_arg, sql, params):
        if sql == "INSERT Policy":
            raise RuntimeError("policy failed")
        if '"Notification"' in sql:
            raise RuntimeError("notify failed")

    monkeypatch.setattr(run_sync_mod.pg_writer, "execute_with_savepoint", fake_execute)

    summary = run_sync_mod.run(tmp_path, tmp_path / "state", 1, "postgres://fake")

    assert "policy P_A: policy failed" in summary["errors"]
    assert "notification write failed: notify failed" in summary["errors"]
    assert conn.closed is True


def test_run_notification_uses_target_account_and_forward_note(tmp_path, monkeypatch):
    conn = FakeRunConn()
    seen_notification_params = []
    monkeypatch.setenv("NOTIFY_TARGET_ACCOUNT", "gloriahao")
    monkeypatch.setenv("NOTIFY_FORWARD_NOTE", "请把这个问题转给邵子渊")
    monkeypatch.setitem(sys.modules, "psycopg2", types.SimpleNamespace(connect=lambda _: conn))
    monkeypatch.setattr(run_sync_mod, "collect_policy_rows",
                        lambda vault, version: ([{"pipeline_pid": "P_A"}], []))
    monkeypatch.setattr(run_sync_mod, "collect_relation_rows", lambda vault, version: [])
    monkeypatch.setattr(run_sync_mod.pg_writer, "build_policy_upsert",
                        lambda row: ("INSERT Policy", {"pid": row["pipeline_pid"]}))

    def fake_build_notification_insert(**kw):
        seen_notification_params.append(kw)
        return ("INSERT INTO \"Notification\"", kw)

    monkeypatch.setattr(run_sync_mod.pg_writer, "build_notification_insert",
                        fake_build_notification_insert)

    def fake_execute(conn_arg, sql, params):
        if sql == "INSERT Policy":
            raise RuntimeError("policy failed")

    monkeypatch.setattr(run_sync_mod.pg_writer, "execute_with_savepoint", fake_execute)

    run_sync_mod.run(tmp_path, tmp_path / "state", 1, "postgres://fake")

    assert seen_notification_params[0]["target_user_id"] == "gloriahao"
    assert seen_notification_params[0]["body"].startswith("请把这个问题转给邵子渊\n")
