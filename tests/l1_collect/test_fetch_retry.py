import json
from pathlib import Path
import scripts.l1_collect.step4_fetch as s4


class _Res:
    def __init__(self, via, body=""):
        self.via = via; self.body = body


def test_fetch_retries_once_then_succeeds(tmp_path, monkeypatch):
    calls = {"n": 0}
    def fake_fetch(url):
        calls["n"] += 1
        return _Res("fetch_error") if calls["n"] == 1 else _Res("firecrawl", "正文够长")
    monkeypatch.setattr(s4, "fetch_article", fake_fetch)
    inp = tmp_path / "cand.jsonl"
    inp.write_text(json.dumps({"url": "http://x.gov.cn/a", "title": "t"}) + "\n", encoding="utf-8")
    success, error = s4.fetch_candidates(inp, tmp_path / "fetch", tmp_path / "ferr.txt")
    assert calls["n"] == 2 and success == 1 and error == 0


def test_fetch_still_fails_after_retry_logged(tmp_path, monkeypatch):
    monkeypatch.setattr(s4, "fetch_article", lambda url: _Res("fetch_error"))
    inp = tmp_path / "cand.jsonl"
    inp.write_text(json.dumps({"url": "http://x.gov.cn/a", "title": "t"}) + "\n", encoding="utf-8")
    success, error = s4.fetch_candidates(inp, tmp_path / "fetch", tmp_path / "ferr.txt")
    assert success == 0 and error == 1
    assert (tmp_path / "ferr.txt").read_text(encoding="utf-8").strip() == "http://x.gov.cn/a"
