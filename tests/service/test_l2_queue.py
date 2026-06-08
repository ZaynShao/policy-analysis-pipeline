from scripts.service.l2_queue import (
    QueueItem, enqueue, enqueue_batch, read_queue, next_item, mark_complete,
)

def test_enqueue_and_read(tmp_path):
    p = tmp_path / "q.jsonl"
    enqueue(p, QueueItem("P_A", "cron", "normal", "2026-06-06T09:00:00"))
    items = read_queue(p)
    assert len(items) == 1
    assert items[0].pid == "P_A"

def test_enqueue_dedup_same_pid(tmp_path):
    p = tmp_path / "q.jsonl"
    enqueue(p, QueueItem("P_A", "cron", "normal", "t1"))
    enqueue(p, QueueItem("P_A", "cron", "normal", "t2"))
    assert len(read_queue(p)) == 1

def test_enqueue_upgrades_priority(tmp_path):
    p = tmp_path / "q.jsonl"
    enqueue(p, QueueItem("P_A", "cron", "normal", "t1"))
    enqueue(p, QueueItem("P_A", "manual", "high", "t2"))
    items = read_queue(p)
    assert len(items) == 1
    assert items[0].priority == "high"
    assert items[0].trigger == "manual"

def test_next_item_high_before_normal(tmp_path):
    p = tmp_path / "q.jsonl"
    enqueue(p, QueueItem("P_A", "cron", "normal", "t1"))
    enqueue(p, QueueItem("P_B", "manual", "high", "t2"))
    assert next_item(p).pid == "P_B"

def test_next_item_fifo_within_priority(tmp_path):
    p = tmp_path / "q.jsonl"
    enqueue(p, QueueItem("P_A", "cron", "normal", "t1"))
    enqueue(p, QueueItem("P_B", "cron", "normal", "t2"))
    assert next_item(p).pid == "P_A"

def test_enqueue_batch(tmp_path):
    p = tmp_path / "q.jsonl"
    enqueue_batch(p, ["P_A", "P_B", "P_C"], "cron", "normal", "t1")
    assert len(read_queue(p)) == 3

def test_mark_complete_removes(tmp_path):
    p = tmp_path / "q.jsonl"
    enqueue_batch(p, ["P_A", "P_B"], "cron", "normal", "t1")
    mark_complete(p, "P_A")
    pids = [i.pid for i in read_queue(p)]
    assert pids == ["P_B"]

def test_next_item_empty_returns_none(tmp_path):
    assert next_item(tmp_path / "empty.jsonl") is None
