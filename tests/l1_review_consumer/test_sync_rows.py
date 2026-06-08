from scripts.l1_review_consumer.sync_l1_pool import pool_row_to_pg, build_upsert


def _pool_row():
    return {"kind": "fetch_fail", "ref": "https://swt.hebei.gov.cn/x.html",
            "reason": "fetch_failed", "suggested_action": "retry",
            "confidence": None, "evidence": "河北省商务厅 swt.hebei.gov.cn",
            "channel": "河北省商务厅", "run_label": "seed_fixture"}


def test_pool_row_to_pg_maps_fields():
    pg = pool_row_to_pg(_pool_row())
    assert pg["pipelineKind"] == "fetch_fail"
    assert pg["pipelineRef"] == "https://swt.hebei.gov.cn/x.html"
    assert pg["dedupeKey"] == "fetch_fail::https://swt.hebei.gov.cn/x.html"
    assert pg["verdict"] is None          # 进池=未判
    assert pg["suggestedAction"] == "retry"
    assert pg["channel"] == "河北省商务厅"


def test_build_upsert_does_not_overwrite_judged():
    pg = pool_row_to_pg(_pool_row())
    sql, params = build_upsert(pg)
    # 幂等 upsert,且只在未判时更新(别覆盖人已判的 verdict)
    assert "ON CONFLICT" in sql and '"dedupeKey"' in sql
    assert 'verdict' not in sql.split("DO UPDATE SET")[1].split("WHERE")[0]
    assert '"verdict" IS NULL' in sql
    assert len(params) == len(pg)
