from scripts.service.l2_queue import read_queue
from scripts.l1_collect.run_incremental import enqueue_ingested


def test_enqueue_ingested_writes_queue_items(tmp_path):
    q = tmp_path / "l2_queue.jsonl"
    enqueue_ingested(q, ["P-001", "P-002"], requested_at="2026-06-10T09:00:00+08:00")
    items = read_queue(q)
    assert [i.pid for i in items] == ["P-001", "P-002"]
    assert all(i.trigger == "l1_incremental" and i.priority == "normal" for i in items)


def test_enqueue_ingested_empty_is_noop(tmp_path):
    q = tmp_path / "l2_queue.jsonl"
    enqueue_ingested(q, [], requested_at="2026-06-10T09:00:00+08:00")
    assert not q.exists()
