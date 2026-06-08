import json
from scripts.l1_review_consumer.poll_l1_verdicts import (
    remove_from_pool, persist_envelope,
)


def test_remove_from_pool_drops_matching_kind_ref(tmp_path):
    pool = tmp_path / "pool.jsonl"
    pool.write_text(
        json.dumps({"kind": "gate", "ref": "p1"}, ensure_ascii=False) + "\n" +
        json.dumps({"kind": "sweep", "ref": "p2"}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    remove_from_pool(pool, kind="gate", ref="p1")
    left = [json.loads(l) for l in pool.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    assert len(left) == 1 and left[0]["ref"] == "p2"


def test_remove_from_pool_keeps_same_ref_other_kind(tmp_path):
    # (kind,ref) 复合键:同 ref 不同 kind 不能误删
    pool = tmp_path / "pool.jsonl"
    pool.write_text(
        json.dumps({"kind": "gate", "ref": "p1"}, ensure_ascii=False) + "\n" +
        json.dumps({"kind": "sweep", "ref": "p1"}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    remove_from_pool(pool, kind="gate", ref="p1")
    left = [json.loads(l) for l in pool.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    assert len(left) == 1 and left[0]["kind"] == "sweep"


def test_persist_envelope_idempotent_by_idem_key(tmp_path):
    sink = tmp_path / "verdicts.jsonl"
    assert persist_envelope(sink, {"idem_key": "gate:p1:r1", "kind": "gate"}) is True
    assert persist_envelope(sink, {"idem_key": "gate:p1:r1", "kind": "gate"}) is False
    rows = [json.loads(l) for l in sink.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    assert len(rows) == 1
