from pathlib import Path
from scripts.l1_collect import review_pool as rp


def _entry(kind="gate", ref="r1"):
    return {"kind": kind, "ref": ref, "reason": "low_conf", "suggested_action": "review",
            "confidence": 0.4, "evidence": "ev", "channel": "ch", "run_label": "run1"}


def test_append_writes_and_dedups(tmp_path):
    pool = tmp_path / "pool.jsonl"
    assert rp.append(_entry(), pool_path=pool) is True
    assert rp.append(_entry(), pool_path=pool) is False          # 同 (kind,ref) 去重
    assert rp.append(_entry(ref="r2"), pool_path=pool) is True
    rows = rp.load(pool_path=pool)
    assert len(rows) == 2
    assert {r["ref"] for r in rows} == {"r1", "r2"}


def test_append_different_kind_same_ref_not_deduped(tmp_path):
    pool = tmp_path / "pool.jsonl"
    rp.append(_entry(kind="gate", ref="x"), pool_path=pool)
    assert rp.append(_entry(kind="sweep", ref="x"), pool_path=pool) is True   # kind 不同→不去重
    assert len(rp.load(pool_path=pool)) == 2


def test_summarize_counts_by_kind(tmp_path):
    pool = tmp_path / "pool.jsonl"
    rp.append(_entry(kind="gate", ref="a"), pool_path=pool)
    rp.append(_entry(kind="fetch_fail", ref="b"), pool_path=pool)
    rp.append(_entry(kind="fetch_fail", ref="c"), pool_path=pool)
    s = rp.summarize(pool_path=pool)
    assert s == {"gate": 1, "fetch_fail": 2}


def test_load_missing_returns_empty(tmp_path):
    assert rp.load(pool_path=tmp_path / "nope.jsonl") == []


from scripts.l1_collect.channel_catalog import Channel, ChannelStatus


def test_candidate_entry_shape():
    from scripts.l1_collect import review_pool as rp
    ch = Channel(city="浙江省商务厅", province="浙江省", level="省", city_code="330000",
                 channel_type="商务", root_domain="x.zj.gov.cn", list_url="http://x.zj.gov.cn/l",
                 source="discovery", status=ChannelStatus.候选)
    e = rp.candidate_entry(ch)
    assert e["kind"] == "checkpoint" and e["ref"] == "x.zj.gov.cn"
    assert e["suggested_action"] == "promote" and "商务" in e["evidence"]
