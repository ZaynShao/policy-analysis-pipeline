from scripts.sync.pg_writer import build_policy_upsert, build_relation_upsert

def test_policy_upsert_targets_pipeline_pid_conflict():
    row = {
        "pipeline_pid": "P_2024_NDRC_718", "pipeline_version": 1,
        "importance": "MAJOR", "pipeline_scores": "{}", "pipeline_themes": "[]",
        "pipeline_impact": "x", "comprehensive": True,
    }
    sql, params = build_policy_upsert(row)
    assert "ON CONFLICT" in sql
    assert "pipeline_pid" in sql or '"pipelinePid"' in sql
    assert "P_2024_NDRC_718" in params.values() if isinstance(params, dict) else "P_2024_NDRC_718" in params

def test_policy_upsert_respects_importance_override():
    """importance 字段只在 importanceOverride IS NULL 时更新——核心约束。"""
    row = {
        "pipeline_pid": "P_X", "pipeline_version": 1, "importance": "MAJOR",
        "pipeline_scores": "{}", "pipeline_themes": "[]", "pipeline_impact": "x",
        "comprehensive": False,
    }
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
