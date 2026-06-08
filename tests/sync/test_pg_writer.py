import pytest

from scripts.sync.pg_writer import (
    build_policy_upsert, build_relation_upsert, execute_with_savepoint,
)

def _policy_row():
    return {
        "pipeline_pid": "P_2024_NDRC_718", "pipeline_version": 1,
        "importance": "MAJOR", "pipeline_scores": "{}", "pipeline_themes": "[]",
        "pipeline_impact": "x", "comprehensive": True,
        "title": "标题", "issuer": "发文机关", "issue_date": "2025-05-27",
        "content": "正文", "source": "AUTO", "doc_number": "文号",
        "source_url": "https://example.com", "region": "全国", "level": "国家",
    }

def test_policy_upsert_targets_pipeline_pid_conflict():
    row = _policy_row()
    sql, params = build_policy_upsert(row)
    assert "ON CONFLICT" in sql
    assert "pipeline_pid" in sql or '"pipelinePid"' in sql
    assert "P_2024_NDRC_718" in params.values() if isinstance(params, dict) else "P_2024_NDRC_718" in params

def test_policy_upsert_writes_core_not_null_fields():
    row = _policy_row()
    sql, params = build_policy_upsert(row)
    for col in ['"title"', '"issuer"', '"issueDate"', '"content"',
                '"source"', '"docNumber"', '"sourceUrl"', '"region"',
                '"level"', '"updatedAt"']:
        assert col in sql
    assert '"updatedAt"' in sql
    assert 'now()' in sql
    assert '%(source)s::"PolicySource"' in sql
    assert "importanceOverride" in sql
    assert "IS NULL" in sql
    for key in ["title", "issuer", "issue_date", "content", "source",
                "doc_number", "source_url", "region", "level"]:
        assert key in params

def test_policy_upsert_respects_importance_override():
    """importance 字段只在 importanceOverride IS NULL 时更新——核心约束。"""
    row = _policy_row()
    sql, _ = build_policy_upsert(row)
    # importance 的 DO UPDATE 子句必须带 override 守卫
    assert "importanceOverride" in sql or "importance_override" in sql
    assert "IS NULL" in sql

def test_relation_upsert_uses_cuid_fks():
    row = {
        "from_pid": "P_A", "to_pid": "P_B", "relation_type": "derives_from",
        "confidence": 0.9, "evidence": "e", "pipeline_version": 1,
    }
    sql, params = build_relation_upsert(row, from_cuid="cuid_a", to_cuid="cuid_b")
    assert "ON CONFLICT" in sql
    vals = list(params.values()) if isinstance(params, dict) else list(params)
    assert "cuid_a" in vals and "cuid_b" in vals
    assert "derives_from" in vals

class FakeCursor:
    def __init__(self, seen, fail_on=None):
        self.seen = seen
        self.fail_on = fail_on

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.seen.append(sql)
        if sql == self.fail_on:
            raise RuntimeError("boom")

class FakeConn:
    def __init__(self, fail_on=None):
        self.seen = []
        self.fail_on = fail_on

    def cursor(self):
        return FakeCursor(self.seen, self.fail_on)

def test_execute_with_savepoint_releases_on_success():
    conn = FakeConn()
    execute_with_savepoint(conn, "INSERT ok", {"x": 1})
    assert conn.seen == ["SAVEPOINT sp", "INSERT ok", "RELEASE SAVEPOINT sp"]

def test_execute_with_savepoint_rolls_back_and_reraises_on_failure():
    conn = FakeConn(fail_on="INSERT bad")
    with pytest.raises(RuntimeError):
        execute_with_savepoint(conn, "INSERT bad", {"x": 1})
    assert conn.seen == ["SAVEPOINT sp", "INSERT bad", "ROLLBACK TO SAVEPOINT sp"]

def test_build_notification_insert():
    from scripts.sync.pg_writer import build_notification_insert
    sql, params = build_notification_insert(level="ERROR", title="run_sync 失败", body="2 errors", source="sync")
    assert '"Notification"' in sql
    assert '"targetUserId"' in sql
    assert 'gen_random_uuid()::text' in sql
    assert '"createdAt"' not in sql
    assert '::"NotificationLevel"' in sql
    assert params["level"] == "ERROR" and params["source"] == "sync"
    assert params["target_user_id"] is None

def test_build_notification_insert_targets_user_id():
    from scripts.sync.pg_writer import build_notification_insert
    sql, params = build_notification_insert(level="ERROR", title="run_sync 失败", body="2 errors",
                                            source="sync", target_user_id="gloriahao")
    assert '"Notification"' in sql
    assert '"targetUserId"' in sql
    assert params["target_user_id"] == "gloriahao"

def test_build_commentary_upsert():
    from scripts.sync import pg_writer
    row = {
        "commentary_id": "C_abc", "title": "标题", "evidence": "摘录",
        "signal_role": "risk", "confidence": 0.72, "source_account": "中电联",
        "business_tag": "power",
        "theme_ids": '["power_market"]',
        "related_policy_pids": '["P_2026_SC_x","P_missing"]',
        "source_path": "0_raw/commentaries/x.md", "pipeline_version": 1,
    }
    sql, params = pg_writer.build_commentary_upsert(row)
    assert 'INSERT INTO "CommentarySignal"' in sql
    assert 'ON CONFLICT ("commentaryId") DO UPDATE' in sql
    assert '%(theme_ids)s::jsonb' in sql
    assert '%(related_policy_pids)s::jsonb' in sql
    assert params["commentary_id"] == "C_abc"
    assert params["related_policy_pids"] == '["P_2026_SC_x","P_missing"]'  # 悬挂 pid 原样留
    assert params["business_tag"] == "power"
