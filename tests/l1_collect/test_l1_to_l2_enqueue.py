import json
import inspect

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


# --- C1 fixes ---

def test_ingest_extracted_writes_to_out_dir_not_default(tmp_path):
    """C1: ingest_extracted 的 out_dir 参数使写入到指定目录而非 POLICIES_DIR。"""
    from scripts.l1_collect.step5_ingest import ingest_extracted
    in_dir = tmp_path / "passed"
    in_dir.mkdir()
    (in_dir / "x.json").write_text(json.dumps({
        "url": "https://www.gov.cn/zhengce/test-c1", "title": "测试政策C1",
        "official_number": "", "date": "2026-06-01", "issuer": "测试部",
        "body": "正文" * 300, "city": "", "city_code": "", "province": "",
        "channel_type": "", "via": "trafilatura",
    }, ensure_ascii=False), encoding="utf-8")
    out_dir = tmp_path / "vault_policies"
    out_dir.mkdir()
    ok, fail, pids = ingest_extracted(in_dir, tmp_path / "log.jsonl", out_dir=out_dir)
    assert ok == 1 and len(pids) == 1
    assert list(out_dir.glob("*.md"))  # 写进了指定 out_dir


def test_run_channel_passes_vault_dir_as_out_dir():
    """C1 回归锚: _run_channel 的 ingest_extracted 调用必须带 out_dir=cfg.vault_dir。"""
    from scripts.l1_collect import run_incremental
    src = inspect.getsource(run_incremental._run_channel)
    assert "out_dir=cfg.vault_dir" in src
