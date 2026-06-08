import json
from pathlib import Path
from scripts.l1_collect import run_incremental as ri
from scripts.l1_collect import review_pool as rp


def _write_ext(ext_dir: Path, name: str, title: str):
    ext_dir.mkdir(parents=True, exist_ok=True)
    (ext_dir / f"{name}.json").write_text(json.dumps(
        {"url": "http://x.gov.cn/a", "title": title, "body": "正文"}, ensure_ascii=False),
        encoding="utf-8")


def test_review_queue_goes_to_pool_not_rejects(tmp_path):
    ext = tmp_path / "ext"; _write_ext(ext, "doc1", "某灰区标题")
    pool = tmp_path / "pool.jsonl"
    review_dir = tmp_path / "review"
    # llm 返回低置信非政策 → gate action=review_queue
    def llm(system, user):
        return json.dumps({"label": "non_policy_news", "confidence": 0.3, "evidence": "灰"})
    res = ri._gate_extracted_dir(
        ext, tmp_path / "passed", tmp_path / "comm",
        tmp_path / "quar" / "gate_rejects.jsonl", llm,
        pool_path=pool, review_dir=review_dir)
    n_pass, n_comm, n_rej, n_review = res
    assert (n_pass, n_comm, n_rej, n_review) == (0, 0, 0, 1)
    rows = rp.load(pool_path=pool)
    assert len(rows) == 1 and rows[0]["kind"] == "gate" and rows[0]["ref"] == "doc1"
    assert (review_dir / "doc1.json").exists()           # ext 项保留供回灌
    # gate_rejects.jsonl 不含该项
    rej = tmp_path / "quar" / "gate_rejects.jsonl"
    assert not rej.exists() or rej.read_text(encoding="utf-8").strip() == ""


def test_real_reject_still_quarantined(tmp_path):
    ext = tmp_path / "ext"; _write_ext(ext, "doc2", "普通新闻")
    pool = tmp_path / "pool.jsonl"
    def llm(system, user):
        return json.dumps({"label": "non_policy_news", "confidence": 0.95, "evidence": "新闻"})
    res = ri._gate_extracted_dir(
        ext, tmp_path / "passed", tmp_path / "comm",
        tmp_path / "quar" / "gate_rejects.jsonl", llm,
        pool_path=pool, review_dir=tmp_path / "review")
    assert res == (0, 0, 1, 0)
    assert rp.load(pool_path=pool) == []
    assert (tmp_path / "quar" / "gate_rejects.jsonl").exists()
