import json
from pathlib import Path

from scripts.l1_collect.commentary_ingest.ledger import (
    load_seen_urls, record_dispositions, write_last_run,
)


def test_load_seen_urls_reads_vault_frontmatter(tmp_path):
    com = tmp_path / "vault" / "0_raw" / "commentaries"
    com.mkdir(parents=True)
    (com / "a.md").write_text(
        "---\ntitle: A\nsource_url: https://mp.weixin.qq.com/s/" + "a" * 22
        + "\nsource: wewe-rss\n---\n\n# A\n正文\n", encoding="utf-8")
    seen = load_seen_urls(tmp_path / "vault", tmp_path / "state")
    assert "https://mp.weixin.qq.com/s/" + "a" * 22 in seen


def test_load_seen_urls_includes_ledger(tmp_path):
    state = tmp_path / "state" / "commentary_ingest"
    state.mkdir(parents=True)
    (state / "processed_ids.jsonl").write_text(
        json.dumps({"id": "x", "url": "https://mp.weixin.qq.com/s/" + "c" * 22,
                    "disposition": "skip_junk"}) + "\n", encoding="utf-8")
    seen = load_seen_urls(tmp_path / "vault", tmp_path / "state")
    assert "https://mp.weixin.qq.com/s/" + "c" * 22 in seen


def test_record_dispositions_appends_jsonl(tmp_path):
    record_dispositions(tmp_path / "state", [
        {"id": "1", "url": "u1", "disposition": "ingest", "reasons": []},
    ])
    record_dispositions(tmp_path / "state", [
        {"id": "2", "url": "u2", "disposition": "skip_junk", "reasons": ["招聘"]},
    ])
    lines = (tmp_path / "state" / "commentary_ingest" / "processed_ids.jsonl"
             ).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_write_last_run_writes_summary(tmp_path):
    write_last_run(tmp_path / "state", {"ingested": 3, "token_status": "valid"})
    rec = json.loads((tmp_path / "state" / "commentary_ingest" / "last_run.json"
                      ).read_text(encoding="utf-8"))
    assert rec["ingested"] == 3
    assert "ran_at" in rec
